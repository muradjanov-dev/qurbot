from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from app.core.config import settings
from app.core.metrics import match_method_total
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.domain.matching.models import CandidateMatch, MatchDecision, MatchStatus
from app.domain.matching.scorer import score_and_rank_candidates
from app.domain.models import NormalizedQuery
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.domain.parsing.parser import is_qty_orderable, parse_basket_lines
from app.llm.client import LLMClient
from app.llm.models import (
    BatchLineDecision,
    BatchLineInput,
    DisambiguationCandidateInput,
)


@dataclass(frozen=True)
class _DeterministicMatch:
    """What Stages 0-2 produced for one line, plus what Stage 3 would need.

    Carrying the candidates back out of the deterministic pass is what makes
    batching possible: the caller collects every unresolved line first, then
    asks the model about all of them in one request.
    """

    parsed_line: ParsedLine
    query: NormalizedQuery
    decision: MatchDecision
    candidates: list[CandidateMatch]


class CatalogService:
    def __init__(
        self,
        catalog_repo: CatalogRepository,
        ops_repo: OpsRepository,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.catalog_repo = catalog_repo
        self.ops_repo = ops_repo
        self.llm_client = llm_client or LLMClient(session=catalog_repo.session)

    async def guide_customer(self, message_text: str, lang: str = "uz_latn") -> str | None:
        """What to tell a customer whose message could not be read as an order.

        Returns None when the model has nothing to offer, so the caller can fall
        back to the fixed string: a customer must always get an answer, even
        when the model is out of budget or unreachable.
        """
        return await self.llm_client.guide_customer(message_text, lang=lang)

    async def _match_deterministic(
        self,
        parsed_line: ParsedLine,
        category_ids: Sequence[int] | None = None,
    ) -> _DeterministicMatch:
        """Stages 0-2: normalize, exact alias lookup, trigram + attribute scoring.

        No network, no LLM. `category_ids` restricts Stage 2 candidates. It is
        supplied when the caller already knows the category (the shop upload
        wizard asks for it up front), which keeps unrelated products from
        consuming the candidate limit before scoring runs.
        """
        # Stage 0: Normalize text and extract feature bag
        query = normalize_query(parsed_line.parsed_name)

        # Stage 1: Exact alias hash lookup
        alias = await self.catalog_repo.get_approved_alias(query.text_norm)
        if alias:
            await self.catalog_repo.record_alias_hit(alias.id)
            canonical = await self.catalog_repo.get(alias.canonical_id)
            if canonical:
                cand = CandidateMatch(
                    canonical_id=canonical.id,
                    slug=canonical.slug,
                    name_uz=canonical.name_uz,
                    brand=canonical.brand,
                    attributes=canonical.attributes,
                    search_doc=canonical.search_doc,
                    popularity_hits=alias.hit_count + 1,
                    is_exact_alias=True,
                    score=1.0,
                    match_method="alias",
                )
                return _DeterministicMatch(
                    parsed_line=parsed_line,
                    query=query,
                    decision=MatchDecision(
                        canonical_id=canonical.id,
                        status="auto_accept",
                        confidence=1.0,
                        candidates=[cand],
                        method="alias",
                        needs_review=False,
                    ),
                    candidates=[cand],
                )

        # Stage 2: Candidate search + multi-factor re-ranking
        raw_candidates = await self.catalog_repo.search_canonical_products(
            query.text_norm, limit=20, category_ids=category_ids
        )
        if not raw_candidates and category_ids:
            # The owner may have filed the product under the wrong category.
            # Retrying unscoped keeps a mis-categorised listing matchable
            # instead of dropping it into the unmatched queue.
            raw_candidates = await self.catalog_repo.search_canonical_products(
                query.text_norm, limit=20
            )

        candidate_matches: list[CandidateMatch] = [
            CandidateMatch(
                canonical_id=c.id,
                slug=c.slug,
                name_uz=c.name_uz,
                brand=c.brand,
                attributes=c.attributes,
                search_doc=c.search_doc,
                popularity_hits=0,
                is_exact_alias=False,
            )
            for c in raw_candidates
        ]

        decision = score_and_rank_candidates(
            query=query,
            candidates=candidate_matches,
            auto_accept_threshold=settings.match_auto_accept_threshold,
            margin_threshold=settings.match_margin_threshold,
            ask_user_threshold=settings.match_ask_user_threshold,
        )

        return _DeterministicMatch(
            parsed_line=parsed_line,
            query=query,
            decision=decision,
            candidates=candidate_matches,
        )

    @staticmethod
    def _needs_llm(match: _DeterministicMatch) -> bool:
        """Every line the search is not certain about, the model looks at.

        Trigram scoring is fast and free, so it goes first and keeps what it is
        sure of. The band below auto-accept is where accuracy is actually lost:
        a line at 0.6 is a coin the search is not qualified to flip, and it used
        to be handed straight to the customer as "pick one of three". The model
        either settles it or writes the question worth asking -- and because the
        basket is batched, looking at more lines costs no extra round trip.

        A line with no candidates at all goes too, and matters most: that is the
        "katalogda topilmadi" the customer sees for a product the catalog does
        carry, under a name they did not use. With nothing to choose from the
        model cannot pick an id, but it can say what the line means, and the
        search runs again on that.

        Left alone only: an exact approved alias. A human already confirmed
        that answer, it costs nothing, and asking the model to review it can
        only make it worse.
        """
        if match.decision.method == "alias":
            return False
        return match.decision.status != "auto_accept"

    @staticmethod
    def _to_batch_input(match: _DeterministicMatch, line_no: int) -> BatchLineInput:
        """Package one unresolved line for the batched Stage 3 call."""
        return BatchLineInput(
            line_no=line_no,
            raw_text=match.parsed_line.raw_text,
            normalized_text=match.query.text_norm,
            candidates=[
                DisambiguationCandidateInput(
                    canonical_id=c.canonical_id,
                    name_uz=c.name_uz,
                    brand=c.brand,
                    attributes=c.attributes if isinstance(c.attributes, dict) else {},
                )
                for c in match.candidates[:8]
            ],
        )

    async def _apply_llm_decision(
        self,
        match: _DeterministicMatch,
        answer: BatchLineDecision,
    ) -> MatchDecision:
        """Fold one model answer into the deterministic decision for that line."""
        canonical_id = answer.canonical_id
        if canonical_id is None or answer.confidence < settings.llm_alias_writeback_min_confidence:
            # Not strong enough to move the match. The question is still worth
            # keeping: it is the one thing that can resolve the line, and it
            # costs the customer a single tap.
            if answer.question:
                return replace(match.decision, clarify_question=answer.question)
            return match.decision

        # Self-learning feedback loop: once an admin approves this alias,
        # Stage 1 answers the same query for free from then on.
        await self.catalog_repo.create_unapproved_alias(
            canonical_id=canonical_id,
            alias_norm=match.query.text_norm,
            alias_raw=match.parsed_line.raw_text,
            confidence=answer.confidence,
            source="llm",
        )

        matched_cand = next(
            (c for c in match.candidates if c.canonical_id == canonical_id),
            None,
        )
        if not matched_cand:
            canon_db = await self.catalog_repo.get(canonical_id)
            if canon_db:
                matched_cand = CandidateMatch(
                    canonical_id=canon_db.id,
                    slug=canon_db.slug,
                    name_uz=canon_db.name_uz,
                    brand=canon_db.brand,
                    attributes=canon_db.attributes,
                    score=answer.confidence,
                    match_method="llm",
                )

        # A question the model chose to ask outranks its own confidence: it
        # said the difference matters to the buyer, so the buyer decides.
        status: MatchStatus = (
            "auto_accept"
            if answer.confidence >= settings.match_auto_accept_threshold and not answer.question
            else "ask_user"
        )
        return MatchDecision(
            canonical_id=canonical_id,
            status=status,
            confidence=answer.confidence,
            candidates=[matched_cand] if matched_cand else match.decision.candidates,
            method="llm",
            needs_review=(status != "auto_accept"),
            clarify_question=answer.question,
        )

    async def _retry_with_search_term(
        self,
        match: _DeterministicMatch,
        answer: BatchLineDecision,
        current: MatchDecision,
    ) -> MatchDecision:
        """Search again on the wording the model supplied, when nothing was found.

        The worst case turned around: "katalogda topilmadi" for a product the
        catalog carries under a name the customer did not use. The second search
        is deterministic and cheap -- no further model call -- and on success the
        original phrasing is written back as an alias, so the next customer to
        say it that way is answered by Stage 1 for free.
        """
        term = (answer.search_term or "").strip()
        if not term or term == match.query.text_norm:
            return current

        retried = await self._match_deterministic(replace(match.parsed_line, parsed_name=term))
        if retried.decision.canonical_id is None:
            return current

        await self.catalog_repo.create_unapproved_alias(
            canonical_id=retried.decision.canonical_id,
            alias_norm=match.query.text_norm,
            alias_raw=match.parsed_line.raw_text,
            confidence=retried.decision.confidence,
            source="llm",
        )

        # The question survives the rescue: a line the search had to be told
        # about is exactly the one worth confirming with the customer.
        return replace(
            retried.decision,
            method="llm_search",
            needs_review=retried.decision.status != "auto_accept",
            clarify_question=answer.question or retried.decision.clarify_question,
        )

    async def _settle_with_model(
        self,
        match: _DeterministicMatch,
        answer: BatchLineDecision,
    ) -> MatchDecision:
        """Apply the model's answer, then retry the search if it named a better term."""
        decision = await self._apply_llm_decision(match, answer)
        if decision.canonical_id is None and answer.search_term:
            decision = await self._retry_with_search_term(match, answer, decision)
        return decision

    async def _finalize(
        self,
        parsed_line: ParsedLine,
        decision: MatchDecision,
        normalized: str,
        user_id: int | None,
    ) -> None:
        """Stage 4: record what stayed unmatched, then count the method used.

        The unmatched queue is how the catalog grows, so this runs after the
        LLM has had its say -- not before, or every line the model rescued
        would still be filed as a gap.
        """
        if decision.status == "unresolved":
            await self.ops_repo.record_unmatched_query(
                raw_text=parsed_line.raw_text,
                normalized=normalized,
                user_id=user_id,
            )
        match_method_total.labels(method=decision.method).inc()

    async def match_parsed_line(
        self,
        parsed_line: ParsedLine,
        user_id: int | None = None,
        category_ids: Sequence[int] | None = None,
        lang: str = "uz_latn",
    ) -> tuple[ParsedLine, MatchDecision]:
        """Run the whole cascade (Stages 0-4) for a single line."""
        match = await self._match_deterministic(parsed_line, category_ids)
        decision = match.decision

        if self._needs_llm(match):
            batch = await self.llm_client.disambiguate_batch(
                [self._to_batch_input(match, parsed_line.line_no)], lang=lang
            )
            answer = batch.lines.get(parsed_line.line_no)
            if answer is not None:
                decision = await self._settle_with_model(match, answer)

        await self._finalize(parsed_line, decision, match.query.text_norm, user_id)
        return parsed_line, decision

    async def parse_and_match_basket(
        self,
        raw_text: str,
        user_id: int | None = None,
        lang: str = "uz_latn",
    ) -> list[tuple[ParsedLine, MatchDecision]]:
        """Parse raw basket text and match every line, using at most one LLM call.

        Stages 0-2 run for every line first; only the leftovers go to the model,
        and they go together. Asking per line meant a ten-line basket became ten
        sequential round trips, each re-sending the same prompt -- the customer
        waited for the sum of them, and the bill grew the same way.

        If deterministic parsing fails structured extraction (< 50% of lines
        have quantities), the whole message goes to the LLM parser first
        (SPEC §7).
        """
        parsed_lines = parse_basket_lines(raw_text)

        # Check if structured parsing struggled
        if parsed_lines:
            # "Did the parser find structure?", not "is the quantity usable?".
            # Keying this on qty > 0 meant a basket of refused quantities looked
            # like a parse failure and went to the whole-message LLM, which
            # re-read "-5 dona" as 5 -- silently turning a rejected line into a
            # real order. needs_review is the flag the parser sets when it could
            # not extract a quantity at all, which is the case this is for.
            lines_with_qty = sum(
                1 for line in parsed_lines if not line.needs_review and line.parsed_name
            )
            qty_ratio = lines_with_qty / len(parsed_lines)
            if qty_ratio < 0.5 and settings.llm_enabled:
                llm_parsed = await self.llm_client.parse_whole_message(raw_text)
                if llm_parsed.lines:
                    parsed_lines = [
                        ParsedLine(
                            line_no=idx + 1,
                            raw_text=f"{pl.qty} {pl.unit or ''} {pl.name}".strip(),
                            parsed_name=pl.name,
                            qty=pl.qty,
                            unit_code=pl.unit,
                            needs_review=(pl.confidence < 0.8),
                        )
                        for idx, pl in enumerate(llm_parsed.lines)
                    ]

        max_qty = Decimal(settings.basket_max_qty)
        results: list[tuple[ParsedLine, MatchDecision]] = []
        matched: list[tuple[int, _DeterministicMatch]] = []
        pending: list[tuple[int, _DeterministicMatch]] = []

        for line in parsed_lines:
            if not is_qty_orderable(line.qty, max_qty=max_qty):
                # Refused before matching: an unorderable quantity should not
                # consume a catalog lookup or an LLM call, and must never reach
                # the optimizer, where it would produce a meaningless total.
                results.append(
                    (
                        line,
                        MatchDecision(
                            canonical_id=None,
                            status="unresolved",
                            confidence=0.0,
                            candidates=[],
                            method="invalid_qty",
                            needs_review=True,
                        ),
                    )
                )
                continue

            match = await self._match_deterministic(line)
            index = len(results)
            results.append((line, match.decision))
            matched.append((index, match))
            if self._needs_llm(match):
                pending.append((index, match))

        if pending:
            batch = await self.llm_client.disambiguate_batch(
                [self._to_batch_input(match, index) for index, match in pending], lang=lang
            )
            for index, match in pending:
                answer = batch.lines.get(index)
                if answer is None:
                    # The model skipped this line; its deterministic decision
                    # stands rather than being replaced by a guess.
                    continue
                results[index] = (results[index][0], await self._settle_with_model(match, answer))

        for index, match in matched:
            await self._finalize(
                results[index][0], results[index][1], match.query.text_norm, user_id
            )

        return results
