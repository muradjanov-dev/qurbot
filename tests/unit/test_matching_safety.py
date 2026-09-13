from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain.matching.models import CandidateMatch, MatchDecision
from app.domain.matching.safety import attributes_verified
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.llm.client import LLMClient
from app.llm.models import BatchLineDecision
from app.services.catalog_service import CatalogService, _DeterministicMatch


@pytest.mark.parametrize(
    "query", ["fanera 0.3mm", "fanera 3m", "fanera 03m", "fanera 12mm", "paner", "fanera"]
)
async def test_ai_cannot_override_physical_constraints(query: str) -> None:
    candidate = CandidateMatch(1, "fanera-3", "Fanera 3 mm", attributes={"thickness_mm": 3})
    line = ParsedLine(1, query, query, Decimal("10"), "dona")
    decision = MatchDecision(1, "ask_user", 0.6, [candidate])
    repo = AsyncMock()
    repo.get_current.return_value = candidate
    repo.is_matchable.return_value = True
    service = CatalogService(repo, AsyncMock(), LLMClient(mock_mode=True))
    result = await service._apply_llm_decision(
        _DeterministicMatch(line, normalize_query(query), decision, [candidate]),
        BatchLineDecision(1, 1, 0.99),
    )
    assert result.status == "ask_user"
    repo.create_unapproved_alias.assert_not_awaited()


def test_missing_attributes_are_not_verified() -> None:
    assert not attributes_verified(normalize_query("fanera 3mm"), {})


def test_reverse_size_is_physically_equal() -> None:
    assert attributes_verified(normalize_query("fanera 1220x2440"), {"size": "2440x1220"})


@pytest.mark.parametrize("data", [{"lines": None}, {"lines": 1}, {}, []])
def test_malformed_batch_falls_back(data: object) -> None:
    assert LLMClient()._deserialize_batch(data).lines == {}  # type: ignore[arg-type]
