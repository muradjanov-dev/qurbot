from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.config import settings
from app.core.metrics import match_method_total
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.domain.matching.models import CandidateMatch, MatchDecision, MatchStatus
from app.domain.matching.scorer import score_and_rank_candidates
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.domain.parsing.parser import is_qty_orderable, parse_basket_lines
from app.llm.client import LLMClient
from app.llm.models import DisambiguationCandidateInput


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

    async def match_parsed_line(
        self,
        parsed_line: ParsedLine,
        user_id: int | None = None,
        category_ids: Sequence[int] | None = None,
    ) -> tuple[ParsedLine, MatchDecision]:
        """Execute Stage 0 -> Stage 1 -> Stage 2 -> Stage 3 (LLM) -> Stage 4 matching cascade.

        `category_ids` restricts Stage 2 candidates. It is supplied when the
        caller already knows the category (the shop upload wizard asks for it
        up front), which keeps unrelated products from consuming the candidate
        limit before scoring runs.
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
                decision = MatchDecision(
                    canonical_id=canonical.id,
                    status="auto_accept",
                    confidence=1.0,
                    candidates=[cand],
                    method="alias",
                    needs_review=False,
                )
                match_method_total.labels(method="alias").inc()
                return parsed_line, decision

        # Stage 2: Candidate search + Multi-factor Re-ranking
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

        # Stage 3: LLM Disambiguation Fallback (§6 Stage 3)
        # Trigger when Stage 2 is unresolved or score < 0.55, but we have candidates
        if (
            decision.status == "unresolved"
            or decision.confidence < settings.match_ask_user_threshold
        ) and raw_candidates:
            top_candidates = [
                DisambiguationCandidateInput(
                    canonical_id=c.id,
                    name_uz=c.name_uz,
                    brand=c.brand,
                    attributes=c.attributes if isinstance(c.attributes, dict) else {},
                )
                for c in raw_candidates[:8]
            ]

            llm_result = await self.llm_client.disambiguate(
                raw_query=parsed_line.raw_text,
                normalized_query=query.text_norm,
                candidates=top_candidates,
            )

            if llm_result.canonical_id and llm_result.confidence >= 0.70:
                # Self-learning feedback loop: write back alias for future fast lookups
                await self.catalog_repo.create_unapproved_alias(
                    canonical_id=llm_result.canonical_id,
                    alias_norm=query.text_norm,
                    alias_raw=parsed_line.raw_text,
                    confidence=llm_result.confidence,
                    source="llm",
                )

                # Find matched canonical product details
                matched_cand = next(
                    (c for c in candidate_matches if c.canonical_id == llm_result.canonical_id),
                    None,
                )
                if not matched_cand:
                    canon_db = await self.catalog_repo.get(llm_result.canonical_id)
                    if canon_db:
                        matched_cand = CandidateMatch(
                            canonical_id=canon_db.id,
                            slug=canon_db.slug,
                            name_uz=canon_db.name_uz,
                            brand=canon_db.brand,
                            attributes=canon_db.attributes,
                            score=llm_result.confidence,
                            match_method="llm",
                        )

                status: MatchStatus = (
                    "auto_accept"
                    if llm_result.confidence >= settings.match_auto_accept_threshold
                    else "ask_user"
                )
                decision = MatchDecision(
                    canonical_id=llm_result.canonical_id,
                    status=status,
                    confidence=llm_result.confidence,
                    candidates=[matched_cand] if matched_cand else decision.candidates,
                    method="llm",
                    needs_review=(status != "auto_accept"),
                )

        # Stage 4: Unresolved query logging (§6 Stage 4)
        if decision.status == "unresolved":
            await self.ops_repo.record_unmatched_query(
                raw_text=parsed_line.raw_text,
                normalized=query.text_norm,
                user_id=user_id,
            )

        match_method_total.labels(method=decision.method).inc()
        return parsed_line, decision

    async def parse_and_match_basket(
        self,
        raw_text: str,
        user_id: int | None = None,
    ) -> list[tuple[ParsedLine, MatchDecision]]:
        """Parse raw basket text and execute matching cascade for every line.

        If deterministic parsing fails structured extraction (< 50% of lines have quantities),
        calls LLM whole-message parse fallback (§7).
        """
        parsed_lines = parse_basket_lines(raw_text)

        # Check if structured parsing struggled
        if parsed_lines:
            lines_with_qty = sum(1 for line in parsed_lines if line.qty > 0 and line.parsed_name)
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
            res = await self.match_parsed_line(line, user_id=user_id)
            results.append(res)
        return results
