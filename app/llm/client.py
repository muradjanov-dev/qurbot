"""Async LLM client for QurBot supporting gpt-5.6-luna and OpenAI-compatible APIs.

Handles:
- Structured JSON completion requests with retries and jitter.
- Dual-layer caching (Hash -> DB/Redis).
- Daily token budget enforcement.
- Metrics & accounting via OpsRepository (LLMCall logging).
- Seamless offline mock testing mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import llm_cost_usd_total
from app.db.models.ops import LLMCall
from app.db.repositories.ops_repo import OpsRepository
from app.llm.cache import compute_llm_input_hash
from app.llm.models import (
    BatchDisambiguationResult,
    BatchLineDecision,
    BatchLineInput,
    DisambiguationCandidateInput,
    DisambiguationResult,
    LLMParsedLine,
    LLMParseResult,
)
from app.llm.prompts import (
    BATCH_DISAMBIGUATION_SYSTEM_PROMPT,
    DISAMBIGUATION_SYSTEM_PROMPT,
    WHOLE_MESSAGE_SYSTEM_PROMPT,
    format_batch_disambiguation_prompt,
    format_disambiguation_prompt,
    format_whole_message_prompt,
)

logger = logging.getLogger(__name__)

# Values that mean "nobody set a key". Config ships the first, `.env.example`
# the second; either one reaching the API is a configuration mistake, not a
# call worth making.
_PLACEHOLDER_API_KEYS = frozenset({"", "changeme", "placeholder_openai_key"})


class LLMClient:
    """Async client for LLM fallback calls with caching and budgeting."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.session = session
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.llm_model
        self.base_url = (
            base_url or settings.openai_base_url or "https://api.openai.com/v1"
        ).rstrip("/")
        self.mock_mode = mock_mode
        self.timeout = settings.llm_timeout_seconds
        self.max_retries = settings.llm_max_retries

    async def disambiguate(
        self,
        raw_query: str,
        normalized_query: str,
        candidates: list[DisambiguationCandidateInput],
    ) -> DisambiguationResult:
        """Stage 3: Disambiguate a noisy query against top candidates."""
        if not candidates or not settings.llm_enabled:
            return DisambiguationResult(
                canonical_id=None, confidence=0.0, reason="LLM disabled or no candidates"
            )

        prompt_version = settings.llm_prompt_version
        user_prompt = format_disambiguation_prompt(raw_query, normalized_query, candidates)
        input_hash = compute_llm_input_hash("disambiguation", prompt_version, user_prompt)

        # 1. Check cache in database
        cached_result = await self._get_cached_call(input_hash)
        if cached_result:
            try:
                data = json.loads(cached_result)
                return DisambiguationResult(
                    canonical_id=data.get("canonical_id"),
                    confidence=float(data.get("confidence", 0.0)),
                    reason=data.get("reason", "cached"),
                )
            except Exception:
                pass

        # 2. Check token budget
        if not await self._has_token_budget():
            logger.warning("Daily LLM token budget exceeded; skipping Stage 3 disambiguation.")
            return DisambiguationResult(
                canonical_id=None, confidence=0.0, reason="Token budget exceeded"
            )

        # 3. Call LLM API (or Mock)
        if self.mock_mode:
            # Deterministic mock fallback for tests
            data = self._mock_disambiguate(raw_query, candidates)
            await self._record_call(
                purpose="disambiguation",
                prompt_version=prompt_version,
                input_hash=input_hash,
                input_tokens=150,
                output_tokens=30,
                cost_usd=Decimal("0.00045"),
                latency_ms=120,
                cache_hit=False,
                raw_response=json.dumps(data),
            )
            return DisambiguationResult(
                canonical_id=data.get("canonical_id"),
                confidence=float(data.get("confidence", 0.0)),
                reason=data.get("reason", "mock_match"),
            )

        start_time = time.monotonic()
        response_dict, in_toks, out_toks = await self._call_chat_completions(
            system_prompt=DISAMBIGUATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        cost_usd = self._estimate_cost(in_toks, out_toks)
        await self._record_call(
            purpose="disambiguation",
            prompt_version=prompt_version,
            input_hash=input_hash,
            input_tokens=in_toks,
            output_tokens=out_toks,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=False,
            raw_response=json.dumps(response_dict) if response_dict else "{}",
        )

        if not response_dict:
            return DisambiguationResult(
                canonical_id=None, confidence=0.0, reason="Empty LLM response"
            )

        return DisambiguationResult(
            canonical_id=response_dict.get("canonical_id"),
            confidence=float(response_dict.get("confidence", 0.0)),
            reason=str(response_dict.get("reason", "")),
        )

    async def disambiguate_batch(
        self,
        lines: list[BatchLineInput],
        lang: str = "uz_latn",
    ) -> BatchDisambiguationResult:
        """Stage 3 for a whole basket: every unresolved line in one request.

        Per-line calls made a ten-line basket ten sequential round trips, each
        paying the full system prompt again -- the customer waited for the sum
        of them. Batching also gives the model the rest of the basket as
        context, which is exactly what disambiguates a bare grade.

        A line the model does not answer is left out of the result; the caller
        keeps its deterministic decision rather than being handed a guess.
        """
        if not lines or not settings.llm_enabled:
            return BatchDisambiguationResult()

        prompt_version = settings.llm_prompt_version
        user_prompt = format_batch_disambiguation_prompt(lines, lang)
        input_hash = compute_llm_input_hash("batch_disambiguation", prompt_version, user_prompt)

        cached_result = await self._get_cached_call(input_hash)
        if cached_result:
            try:
                return self._deserialize_batch(json.loads(cached_result))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("Cached batch disambiguation payload was unreadable; recomputing")

        if not await self._has_token_budget():
            logger.warning("Daily LLM token budget exceeded; skipping batch disambiguation.")
            return BatchDisambiguationResult()

        if self.mock_mode:
            data = self._mock_disambiguate_batch(lines)
            await self._record_call(
                purpose="batch_disambiguation",
                prompt_version=prompt_version,
                input_hash=input_hash,
                input_tokens=150 * len(lines),
                output_tokens=30 * len(lines),
                cost_usd=Decimal("0.00045") * len(lines),
                latency_ms=140,
                cache_hit=False,
                raw_response=json.dumps(data),
            )
            return self._deserialize_batch(data)

        start_time = time.monotonic()
        response_dict, in_toks, out_toks = await self._call_chat_completions(
            system_prompt=BATCH_DISAMBIGUATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        await self._record_call(
            purpose="batch_disambiguation",
            prompt_version=prompt_version,
            input_hash=input_hash,
            input_tokens=in_toks,
            output_tokens=out_toks,
            cost_usd=self._estimate_cost(in_toks, out_toks),
            latency_ms=latency_ms,
            cache_hit=False,
            raw_response=json.dumps(response_dict) if response_dict else "{}",
        )

        if not response_dict:
            return BatchDisambiguationResult()

        return self._deserialize_batch(response_dict)

    async def parse_whole_message(self, message_text: str) -> LLMParseResult:
        """Whole message parsing fallback when structured parser yields < 50% lines."""
        if not message_text or not settings.llm_enabled:
            return LLMParseResult(lines=[])

        prompt_version = settings.llm_prompt_version
        user_prompt = format_whole_message_prompt(message_text)
        input_hash = compute_llm_input_hash("whole_message_parse", prompt_version, user_prompt)

        cached_result = await self._get_cached_call(input_hash)
        if cached_result:
            try:
                data = json.loads(cached_result)
                return self._deserialize_parse_lines(data)
            except Exception:
                pass

        if not await self._has_token_budget():
            logger.warning("Daily LLM token budget exceeded; skipping whole message parse.")
            return LLMParseResult(lines=[])

        if self.mock_mode:
            data = self._mock_parse_whole_message(message_text)
            await self._record_call(
                purpose="whole_message_parse",
                prompt_version=prompt_version,
                input_hash=input_hash,
                input_tokens=200,
                output_tokens=50,
                cost_usd=Decimal("0.00060"),
                latency_ms=180,
                cache_hit=False,
                raw_response=json.dumps(data),
            )
            return self._deserialize_parse_lines(data)

        start_time = time.monotonic()
        response_dict, in_toks, out_toks = await self._call_chat_completions(
            system_prompt=WHOLE_MESSAGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        cost_usd = self._estimate_cost(in_toks, out_toks)
        await self._record_call(
            purpose="whole_message_parse",
            prompt_version=prompt_version,
            input_hash=input_hash,
            input_tokens=in_toks,
            output_tokens=out_toks,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=False,
            raw_response=json.dumps(response_dict) if response_dict else "{}",
        )

        if not response_dict:
            return LLMParseResult(lines=[])

        return self._deserialize_parse_lines(response_dict)

    # ---------------------------------------------------------------------------
    # Internal HTTP Request Execution
    # ---------------------------------------------------------------------------

    async def _call_chat_completions(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[dict[str, Any] | None, int, int]:
        """Execute request against OpenAI-compatible Chat Completions endpoint."""
        if self.api_key in _PLACEHOLDER_API_KEYS:
            # No key was ever configured, so every request would fail auth after
            # the full timeout-and-retry budget. Refusing here keeps a
            # misconfigured deployment from adding seconds of certain failure to
            # every basket, and keeps tests off the network without pretending
            # the LLM answered.
            logger.warning("LLM API key is a placeholder; skipping call to %s", self.base_url)
            return None, 0, 0

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # NOTE (deviates from SPEC §6 "Temperature 0, max_tokens 300"): the
        # configured model rejects both of those parameters outright --
        # "'max_tokens' is not supported with this model, use
        # 'max_completion_tokens'" and "'temperature' does not support 0 with
        # this model. Only the default (1) value is supported." Sending them
        # returned HTTP 400 on every single call, so Stage 3 silently never
        # worked in production. Temperature is therefore omitted (model default)
        # and the cap uses the parameter the model actually accepts.
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_completion_tokens": settings.llm_max_completion_tokens,
            "response_format": {"type": "json_object"},
        }

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    usage = data.get("usage", {})
                    in_tokens = int(usage.get("prompt_tokens", 0))
                    out_tokens = int(usage.get("completion_tokens", 0))

                    choices = data.get("choices", [])
                    if choices:
                        content_str = choices[0].get("message", {}).get("content", "{}")
                        parsed = json.loads(content_str)
                        return parsed, in_tokens, out_tokens
                    return None, in_tokens, out_tokens
            except Exception as e:
                if attempt < self.max_retries:
                    backoff = (0.5 * (2**attempt)) + random.uniform(0.1, 0.4)
                    await asyncio.sleep(backoff)
                else:
                    logger.error("LLM call failed after %d retries: %s", self.max_retries, e)

        return None, 0, 0

    # ---------------------------------------------------------------------------
    # Accounting & Caching Helpers
    # ---------------------------------------------------------------------------

    async def _get_cached_call(self, input_hash: str) -> str | None:
        if not self.session:
            return None
        try:
            stmt = (
                select(LLMCall)
                .where(LLMCall.input_hash == input_hash)
                .order_by(LLMCall.id.desc())
                .limit(1)
            )
            res = await self.session.execute(stmt)
            call = res.scalars().first()
            if call and call.raw_response:
                # Log cache hit
                ops_repo = OpsRepository(self.session)
                await ops_repo.record_llm_call(
                    purpose=call.purpose,
                    prompt_version=call.prompt_version,
                    input_hash=input_hash,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=Decimal("0.000000"),
                    latency_ms=1,
                    cache_hit=True,
                    raw_response=call.raw_response,
                )
                return call.raw_response
        except Exception:
            pass
        return None

    async def _has_token_budget(self) -> bool:
        """Whether the last 24 hours leave room under the daily token budget.

        The window is the point. Summed over all time, this was not a daily
        budget but a lifetime one: once the project had ever spent 100k tokens,
        every LLM stage switched itself off permanently, silently, and looked
        exactly like a model that had nothing to say.
        """
        if not self.session:
            return True
        try:
            since = datetime.now(UTC) - timedelta(hours=24)
            stmt = select(func.sum(LLMCall.input_tokens + LLMCall.output_tokens)).where(
                LLMCall.created_at >= since
            )
            res = await self.session.execute(stmt)
            total_tokens = int(res.scalar() or 0)

            # Deferred import: the alert reaches the bot to DM the admins, and
            # the dispatcher pulls in handlers -> services -> this module, so a
            # module-scope import would close the cycle.
            from app.services.llm_budget_alert import warn_admins_if_budget_low

            await warn_admins_if_budget_low(self.session, total_tokens)
            return bool(total_tokens < settings.llm_daily_token_budget)
        except Exception:
            return True

    async def _record_call(
        self,
        purpose: str,
        prompt_version: str,
        input_hash: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
        latency_ms: int,
        cache_hit: bool,
        raw_response: str | None = None,
    ) -> None:
        if not self.session:
            return
        try:
            ops_repo = OpsRepository(self.session)
            await ops_repo.record_llm_call(
                purpose=purpose,
                prompt_version=prompt_version,
                input_hash=input_hash,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
                raw_response=raw_response,
            )
            llm_cost_usd_total.inc(float(cost_usd))
        except Exception:
            logger.exception("Failed to record LLM call in DB")

    def _estimate_cost(self, in_tokens: int, out_tokens: int) -> Decimal:
        """Cost estimate for gpt-5.6-luna / modern fast models ($2.5 / 1M in, $10 / 1M out)."""
        cost = (Decimal(in_tokens) * Decimal("0.0000025")) + (
            Decimal(out_tokens) * Decimal("0.000010")
        )
        return cost.quantize(Decimal("0.000001"))

    def _deserialize_batch(self, data: dict[str, Any]) -> BatchDisambiguationResult:
        """Read the model's per-line answers, discarding anything malformed.

        A line whose payload cannot be trusted is dropped rather than defaulted:
        the caller's deterministic decision is a better answer than a fabricated
        one, and silently inventing a canonical_id here would put a product the
        customer never asked for into their basket.
        """
        decisions: dict[int, BatchLineDecision] = {}
        for raw in data.get("lines", []):
            if not isinstance(raw, dict):
                continue
            try:
                line_no = int(raw["line_no"])
            except (KeyError, TypeError, ValueError):
                continue

            raw_canonical = raw.get("canonical_id")
            try:
                canonical_id = int(raw_canonical) if raw_canonical is not None else None
                confidence = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue

            question = raw.get("question")
            question_text = str(question).strip() if question else ""
            search_term = raw.get("search_term")
            search_text = str(search_term).strip() if search_term else ""

            decisions[line_no] = BatchLineDecision(
                line_no=line_no,
                canonical_id=canonical_id,
                confidence=confidence,
                reason=str(raw.get("reason", "")),
                question=question_text or None,
                search_term=search_text or None,
            )
        return BatchDisambiguationResult(lines=decisions)

    def _mock_disambiguate_batch(self, lines: list[BatchLineInput]) -> dict[str, Any]:
        """Offline batch mock: the single-line heuristic applied to each line."""
        answers = []
        for line in lines:
            data = self._mock_disambiguate(line.raw_text, line.candidates)
            answers.append(
                {
                    "line_no": line.line_no,
                    "canonical_id": data.get("canonical_id"),
                    "confidence": data.get("confidence", 0.0),
                    "reason": data.get("reason", "mock_match"),
                    "question": None,
                }
            )
        return {"lines": answers}

    def _deserialize_parse_lines(self, data: dict[str, Any]) -> LLMParseResult:
        raw_lines = data.get("lines", [])
        parsed_lines: list[LLMParsedLine] = []
        for raw_line in raw_lines:
            if not isinstance(raw_line, dict) or not raw_line.get("name"):
                continue
            qty_val = Decimal(str(raw_line.get("qty", 1.0)))
            unit_val = str(raw_line["unit"]) if raw_line.get("unit") else None
            conf_val = float(raw_line.get("confidence", 0.9))
            parsed_lines.append(
                LLMParsedLine(
                    name=str(raw_line["name"]),
                    qty=qty_val,
                    unit=unit_val,
                    confidence=conf_val,
                )
            )
        return LLMParseResult(lines=parsed_lines)

    # ---------------------------------------------------------------------------
    # Mock Heuristics for Offline / Unit Tests
    # ---------------------------------------------------------------------------

    def _mock_disambiguate(
        self,
        raw_query: str,
        candidates: list[DisambiguationCandidateInput],
    ) -> dict[str, Any]:
        """Offline mock disambiguation that intelligently matches synonyms."""
        q_lower = raw_query.lower()

        # Check against candidates
        for c in candidates:
            c_lower = c.name_uz.lower()
            # Synonym checks:
            if "shifer" in c_lower and any(
                w in q_lower for w in ["shipr", "шипр", "shifr", "асбест"]
            ):
                return {
                    "canonical_id": c.canonical_id,
                    "confidence": 0.95,
                    "reason": "Synonym match: shipr -> shifer",
                }
            if "cement" in c_lower and any(
                w in q_lower for w in ["sement", "цемент", "smnt", "m400", "m500"]
            ):
                return {
                    "canonical_id": c.canonical_id,
                    "confidence": 0.92,
                    "reason": "Synonym match: cement",
                }
            if "plitka yelimi" in c_lower and any(
                w in q_lower for w in ["yopishtiruvchi", "kley", "yelim"]
            ):
                return {
                    "canonical_id": c.canonical_id,
                    "confidence": 0.90,
                    "reason": "Semantic match: yopishtiruvchi -> plitka yelimi",
                }
            if "armatura" in c_lower and any(
                w in q_lower for w in ["armatura", "арматура", "d12", "d14"]
            ):
                return {
                    "canonical_id": c.canonical_id,
                    "confidence": 0.94,
                    "reason": "Grade match: armatura",
                }

        # Default fallback to top candidate if candidates available
        if candidates:
            return {
                "canonical_id": candidates[0].canonical_id,
                "confidence": 0.85,
                "reason": "Best semantic match",
            }
        return {"canonical_id": None, "confidence": 0.0, "reason": "No candidate match"}

    def _mock_parse_whole_message(self, message_text: str) -> dict[str, Any]:
        """Offline mock whole message parser."""
        text_lower = message_text.lower()
        if "fanera" in text_lower or "osb" in text_lower:
            return {
                "lines": [
                    {"name": "Fanera 12mm", "qty": 10.0, "unit": "dona", "confidence": 0.95},
                    {"name": "OSB-3 9mm", "qty": 5.0, "unit": "dona", "confidence": 0.95},
                ]
            }
        return {
            "lines": [
                {"name": "Sement M400", "qty": 10.0, "unit": "qop", "confidence": 0.95},
                {"name": "G'isht qizil", "qty": 500.0, "unit": "dona", "confidence": 0.95},
            ]
        }
