import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import app.services.catalog_service as module
from app.core.config import settings
from app.domain.matching.models import CandidateMatch, MatchDecision
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.llm.models import BatchDisambiguationResult, LLMParsedLine, LLMParseResult
from app.services.catalog_service import CatalogService, _DeterministicMatch


async def test_all_ai_stages_share_twelve_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_total_deadline_seconds", 12)
    monkeypatch.setattr(settings, "llm_enabled", True)
    original = ParsedLine(
        1, "faneradan 10ta kerak", "faneradan", Decimal(1), None, needs_review=True
    )
    monkeypatch.setattr(module, "parse_basket_lines", lambda _: [original])

    async def parse(_):
        await asyncio.sleep(6.5)
        return LLMParseResult([LLMParsedLine("fanera", Decimal(10), "dona", 1)])

    async def batch(*args, **kwargs):
        await asyncio.sleep(6.5)
        return BatchDisambiguationResult()

    llm = AsyncMock()
    llm.parse_whole_message.side_effect = parse
    llm.disambiguate_batch.side_effect = batch
    service = CatalogService(AsyncMock(), AsyncMock(), llm)
    candidate = CandidateMatch(1, "fanera", "Fanera 3mm")

    async def deterministic(line, **kwargs):
        return _DeterministicMatch(
            line,
            normalize_query(line.parsed_name),
            MatchDecision(1, "ask_user", 0.6, [candidate]),
            [candidate],
        )

    monkeypatch.setattr(service, "_match_deterministic", deterministic)
    started = time.monotonic()
    results = await service.parse_and_match_basket(original.raw_text)
    assert time.monotonic() - started < 13
    assert results[0][1].status == "ask_user"
    assert results[0][1].candidates[0].canonical_id == 1
    llm.disambiguate_batch.assert_awaited_once()
