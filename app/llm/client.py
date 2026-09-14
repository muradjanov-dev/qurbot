"""Async LLM client for QurBot supporting OpenAI and native Anthropic APIs.

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
import math
import random
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import llm_cost_usd_total, llm_outcome_total
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
from app.llm.pricing import EvaluationBudget, estimate_cost
from app.llm.prompts import (
    BATCH_DISAMBIGUATION_SYSTEM_PROMPT,
    CUSTOMER_GUIDE_SYSTEM_PROMPT,
    DISAMBIGUATION_SYSTEM_PROMPT,
    WHOLE_MESSAGE_SYSTEM_PROMPT,
    format_batch_disambiguation_prompt,
    format_customer_guide_prompt,
    format_disambiguation_prompt,
    format_whole_message_prompt,
)

logger = logging.getLogger(__name__)

# Values that mean "nobody set a key". Config ships the first, `.env.example`
# the second; either one reaching the API is a configuration mistake, not a
# call worth making.
_PLACEHOLDER_API_KEYS = frozenset(
    {"", "changeme", "placeholder_openai_key", "placeholder_anthropic_key"}
)
_http_client: httpx.AsyncClient | None = None

_GUIDE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
    "additionalProperties": False,
}
_DISAMBIGUATION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "canonical_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["canonical_id", "confidence", "reason"],
    "additionalProperties": False,
}
_BATCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_no": {"type": "integer"},
                    "canonical_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "question": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "search_term": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": [
                    "line_no",
                    "canonical_id",
                    "confidence",
                    "reason",
                    "question",
                    "search_term",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}
_WHOLE_MESSAGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "qty": {
                        "type": "string",
                        "description": "Decimal quantity, for example 10 or 0.5",
                    },
                    "unit": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "qty", "unit", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}


async def start_http_client() -> None:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient()


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


@asynccontextmanager
async def http_session() -> AsyncIterator[httpx.AsyncClient]:
    if _http_client is not None:
        yield _http_client
    else:
        # CLI/tests without an application lifecycle still close their sockets.
        async with httpx.AsyncClient() as client:
            yield client


class LLMClient:
    """Async client for LLM fallback calls with caching and budgeting."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        provider: Literal["openai", "anthropic"] | None = None,
        mock_mode: bool = False,
        evaluation_budget: EvaluationBudget | None = None,
    ) -> None:
        self.session = session
        self.provider = provider or settings.llm_provider
        configured_key = (
            settings.anthropic_api_key if self.provider == "anthropic" else settings.openai_api_key
        )
        self.api_key = api_key or configured_key
        self.model = model or settings.llm_model
        configured_base_url = (
            settings.anthropic_base_url
            if self.provider == "anthropic"
            else settings.openai_base_url or "https://api.openai.com/v1"
        )
        self.base_url = (base_url or configured_base_url).rstrip("/")
        self.mock_mode = mock_mode
        self.timeout = settings.llm_timeout_seconds
        self.max_retries = min(1, max(0, settings.llm_max_retries))
        self.last_outcome = "unknown"
        self.last_attempt_count = 0
        self.evaluation_budget = evaluation_budget

    def _validated_single(
        self, data: dict[str, Any], candidates: list[DisambiguationCandidateInput]
    ) -> DisambiguationResult:
        batch = self._deserialize_batch(
            {"lines": [{**data, "line_no": 0}]},
            [BatchLineInput(0, "", "", candidates)],
        )
        answer = batch.lines.get(0)
        if answer is None:
            return DisambiguationResult(None, 0, "invalid_response")
        return DisambiguationResult(answer.canonical_id, answer.confidence, answer.reason)

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
        input_hash = self._cache_hash("disambiguation", prompt_version, user_prompt)

        # 1. Check cache in database
        cached_result = await self._get_cached_call(input_hash)
        if cached_result:
            try:
                data = json.loads(cached_result)
                return self._validated_single(data, candidates)
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
            return self._validated_single(data, candidates)

        start_time = time.monotonic()
        response_dict, in_toks, out_toks = await self._call_chat_completions(
            system_prompt=DISAMBIGUATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=_DISAMBIGUATION_OUTPUT_SCHEMA,
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

        return self._validated_single(response_dict, candidates)

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
        input_hash = self._cache_hash(
            "batch_disambiguation", prompt_version, user_prompt, lang=lang
        )

        cached_result = await self._get_cached_call(input_hash)
        if cached_result:
            try:
                return self._deserialize_batch(json.loads(cached_result), lines)
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
            return self._deserialize_batch(data, lines)

        start_time = time.monotonic()
        response_dict, in_toks, out_toks = await self._call_chat_completions(
            system_prompt=BATCH_DISAMBIGUATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=_BATCH_OUTPUT_SCHEMA,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        validated = self._deserialize_batch(response_dict or {}, lines)
        if response_dict and len(validated.lines) != len(lines):
            self.last_outcome = "invalid_response"

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

        return validated

    async def parse_whole_message(self, message_text: str) -> LLMParseResult:
        """Whole message parsing fallback when structured parser yields < 50% lines."""
        if not message_text or not settings.llm_enabled:
            return LLMParseResult(lines=[])

        prompt_version = settings.llm_prompt_version
        user_prompt = format_whole_message_prompt(message_text)
        input_hash = self._cache_hash("whole_message_parse", prompt_version, user_prompt)

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
            output_schema=_WHOLE_MESSAGE_OUTPUT_SCHEMA,
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

    async def guide_customer(self, message_text: str, lang: str = "uz_latn") -> str | None:
        """Turn a message the parser could not read into a next step the customer can take.

        The fixed "I did not understand" is where people leave: it says nothing
        to someone who wrote "salom" or "fanera bormi?", and the customers this
        bot is for do not experiment with phrasings until one works. The model
        reads what they actually sent and answers with the instruction.

        Returns None whenever the model is unavailable or says nothing usable,
        and the caller falls back to the catalogue string -- guidance is worth a
        call, never worth a silence.
        """
        if not message_text.strip() or not settings.llm_enabled:
            return None

        prompt_version = settings.llm_prompt_version
        user_prompt = format_customer_guide_prompt(message_text, lang)
        input_hash = self._cache_hash("customer_guide", prompt_version, user_prompt, lang=lang)

        cached_result = await self._get_cached_call(input_hash)
        if cached_result:
            try:
                cached_reply = str(json.loads(cached_result).get("reply", "")).strip()
                if cached_reply:
                    return self._trim_guide(cached_reply)
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("Cached guidance payload was unreadable; recomputing")

        if not await self._has_token_budget():
            logger.warning("Daily LLM token budget exceeded; skipping customer guidance.")
            return None

        if self.mock_mode:
            data = {
                "reply": (
                    "Ro'yxatni shunday yozing: miqdor + birlik + nom.\n"
                    "Masalan: 10 dona fanera 12mm"
                )
            }
            await self._record_call(
                purpose="customer_guide",
                prompt_version=prompt_version,
                input_hash=input_hash,
                input_tokens=120,
                output_tokens=40,
                cost_usd=Decimal("0.00043"),
                latency_ms=130,
                cache_hit=False,
                raw_response=json.dumps(data),
            )
            return self._trim_guide(data["reply"])

        start_time = time.monotonic()
        response_dict, in_toks, out_toks = await self._call_chat_completions(
            system_prompt=CUSTOMER_GUIDE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=_GUIDE_OUTPUT_SCHEMA,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        await self._record_call(
            purpose="customer_guide",
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
            return None
        reply = str(response_dict.get("reply", "")).strip()
        return self._trim_guide(reply) if reply else None

    @staticmethod
    def _trim_guide(reply: str) -> str:
        """Cut a runaway answer at the last full line that fits."""
        limit = settings.llm_guide_max_chars
        if len(reply) <= limit:
            return reply
        cut = reply[:limit]
        newline = cut.rfind("\n")
        return (cut[:newline] if newline > 0 else cut).rstrip()

    # ---------------------------------------------------------------------------
    # Internal HTTP Request Execution
    # ---------------------------------------------------------------------------

    async def _call_chat_completions(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, int, int]:
        """Execute one structured completion through the configured provider."""
        self.last_attempt_count = 0
        self.last_outcome = "unavailable"
        if self.api_key in _PLACEHOLDER_API_KEYS:
            # No key was ever configured, so every request would fail auth after
            # the full timeout-and-retry budget. Refusing here keeps a
            # misconfigured deployment from adding seconds of certain failure to
            # every basket, and keeps tests off the network without pretending
            # the LLM answered.
            logger.warning("LLM API key is a placeholder; skipping call")
            return None, 0, 0

        if self.provider == "anthropic":
            url = f"{self.base_url}/messages"
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "model": self.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": settings.llm_max_completion_tokens,
                # QurBot needs a small JSON classification, not agentic reasoning.
                # Opus 5 enables thinking by default, which adds billed tokens and
                # latency without improving this constrained task.
                "thinking": {"type": "disabled"},
            }
            if output_schema is not None:
                payload["output_config"] = {
                    "format": {"type": "json_schema", "schema": output_schema}
                }
        else:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            # The configured OpenAI models reject temperature=0 and max_tokens.
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
            in_tokens = out_tokens = 0
            if self.evaluation_budget is not None and not self.evaluation_budget.reserve(
                self.model, system_prompt, user_prompt, settings.llm_max_completion_tokens
            ):
                self.last_outcome = "budget_exhausted"
                return None, 0, 0
            self.last_attempt_count = attempt + 1
            try:
                async with http_session() as client:
                    async with asyncio.timeout(min(8.0, self.timeout)):
                        resp = await client.post(
                            url, headers=headers, json=payload, timeout=self.timeout
                        )
                    # Authentication, validation and malformed requests cannot
                    # improve on retry.  Only transient upstream failures do.
                    if resp.status_code in (400, 401, 403):
                        self.last_outcome = "rejected"
                        logger.warning("LLM request rejected with HTTP %s", resp.status_code)
                        return None, 0, 0
                    resp.raise_for_status()
                    data = resp.json()

                    usage = data.get("usage", {})
                    if self.provider == "anthropic":
                        in_tokens = int(usage.get("input_tokens", 0))
                        out_tokens = int(usage.get("output_tokens", 0))
                        content_str = next(
                            (
                                block.get("text", "")
                                for block in data.get("content", [])
                                if block.get("type") == "text"
                            ),
                            "",
                        )
                    else:
                        in_tokens = int(usage.get("prompt_tokens", 0))
                        out_tokens = int(usage.get("completion_tokens", 0))
                        choices = data.get("choices", [])
                        content_str = (
                            choices[0].get("message", {}).get("content", "") if choices else ""
                        )
                    if not content_str:
                        return None, in_tokens, out_tokens
                    parsed = json.loads(content_str)
                    if not isinstance(parsed, dict):
                        self.last_outcome = "invalid_response"
                        return None, in_tokens, out_tokens
                    self.last_outcome = "success"
                    return parsed, in_tokens, out_tokens
            except (
                TimeoutError,
                httpx.TimeoutException,
                httpx.TransportError,
                httpx.HTTPStatusError,
            ) as e:
                self.last_outcome = (
                    "timeout"
                    if isinstance(e, TimeoutError | httpx.TimeoutException)
                    else "api_error"
                )
                retryable = not isinstance(e, httpx.HTTPStatusError) or (
                    e.response.status_code == 429 or e.response.status_code >= 500
                )
                if retryable and attempt < self.max_retries:
                    backoff = (0.5 * (2**attempt)) + random.uniform(0.1, 0.4)
                    await asyncio.sleep(backoff)
                else:
                    logger.warning(
                        "LLM call unavailable after %d retries: %s",
                        self.max_retries,
                        type(e).__name__,
                    )
                    return None, 0, 0
            except asyncio.CancelledError:
                self.last_outcome = "deadline"
                llm_outcome_total.labels(outcome="deadline").inc()
                raise
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                self.last_outcome = "invalid_response"
                logger.warning("LLM returned invalid JSON; not retrying")
                return None, in_tokens, out_tokens

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
                .where(
                    LLMCall.input_hash == input_hash,
                    LLMCall.created_at >= datetime.now(UTC) - timedelta(hours=24),
                    LLMCall.cache_hit.is_(False),
                    LLMCall.model == self.model,
                    LLMCall.outcome.in_(["success", "mock"]),
                )
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
                    model=self.model,
                    outcome="cache_hit",
                    attempt_count=0,
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
        outcome: str | None = None,
        attempt_count: int | None = None,
    ) -> None:
        llm_outcome_total.labels(outcome=outcome or self.last_outcome).inc()
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
                model=self.model,
                outcome=outcome or ("mock" if self.mock_mode else self.last_outcome),
                attempt_count=attempt_count
                if attempt_count is not None
                else self.last_attempt_count,
            )
            llm_cost_usd_total.inc(float(cost_usd))
        except Exception:
            logger.exception("Failed to record LLM call in DB")

    def _cache_hash(
        self, purpose: str, prompt_version: str, payload: str, *, lang: str | None = None
    ) -> str:
        """Cache keys cannot cross models, prompt languages or candidate order."""
        return compute_llm_input_hash(
            purpose,
            prompt_version,
            {
                "model": self.model,
                "language": lang,
                "payload": payload,
            },
        )

    def _estimate_cost(self, in_tokens: int, out_tokens: int) -> Decimal:
        cost = estimate_cost(self.model, in_tokens, out_tokens)
        if cost is None:
            self.last_outcome = "unknown_price"
            # Legacy NOT NULL amount: outcome explicitly excludes this zero
            # from being interpreted as a known free call.
            return Decimal("0")
        return cost

    def _deserialize_batch(
        self, data: dict[str, Any], requested_lines: list[BatchLineInput] | None = None
    ) -> BatchDisambiguationResult:
        """Read the model's per-line answers, discarding anything malformed.

        A line whose payload cannot be trusted is dropped rather than defaulted:
        the caller's deterministic decision is a better answer than a fabricated
        one, and silently inventing a canonical_id here would put a product the
        customer never asked for into their basket.
        """
        decisions: dict[int, BatchLineDecision] = {}
        allowed_ids = {
            line.line_no: {candidate.canonical_id for candidate in line.candidates}
            for line in requested_lines or []
        }
        if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
            return BatchDisambiguationResult()
        duplicates: set[int] = set()
        seen: set[int] = set()
        for raw in data["lines"]:
            if not isinstance(raw, dict):
                continue
            if isinstance(raw.get("confidence"), bool) or any(
                raw.get(key) is not None and not isinstance(raw[key], str)
                for key in ("question", "search_term", "reason")
            ):
                continue
            try:
                if type(raw["line_no"]) is not int:
                    continue
                line_no = raw["line_no"]
            except (KeyError, TypeError, ValueError):
                continue

            raw_canonical = raw.get("canonical_id")
            if line_no in seen:
                duplicates.add(line_no)
            seen.add(line_no)
            if raw_canonical is not None and type(raw_canonical) is not int:
                continue
            try:
                canonical_id = int(raw_canonical) if raw_canonical is not None else None
                confidence = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue

            if line_no in decisions or (requested_lines is not None and line_no not in allowed_ids):
                continue
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                continue
            if (
                canonical_id is not None
                and requested_lines is not None
                and canonical_id not in allowed_ids.get(line_no, set())
            ):
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
        return BatchDisambiguationResult(
            lines={key: value for key, value in decisions.items() if key not in duplicates}
        )

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
        if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
            return LLMParseResult(lines=[])
        raw_lines = data.get("lines", [])
        parsed_lines: list[LLMParsedLine] = []
        for raw_line in raw_lines:
            if not isinstance(raw_line, dict) or not raw_line.get("name"):
                continue
            try:
                qty_val = Decimal(str(raw_line["qty"]))
                conf_val = float(raw_line.get("confidence", 0))
            except (KeyError, InvalidOperation, TypeError, ValueError):
                continue
            if (
                not qty_val.is_finite()
                or qty_val <= 0
                or not math.isfinite(conf_val)
                or not 0 <= conf_val <= 1
            ):
                continue
            unit_val = str(raw_line["unit"]) if raw_line.get("unit") else None
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
