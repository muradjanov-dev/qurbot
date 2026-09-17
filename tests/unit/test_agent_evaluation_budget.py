import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.llm.evaluation import reserve_agent_evaluation


def test_live_budget_persists_and_caps_concurrent_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / "budget.json"
    monkeypatch.setattr(settings, "agent_evaluation_budget_path", str(ledger))
    monkeypatch.setattr(settings, "agent_evaluation_budget_usd", Decimal("0.20"))

    def reserve(_: int) -> bool:
        return reserve_agent_evaluation("claude-opus-5", "system", [], [], 2000)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(results) == 1  # Each worst-case reservation is just over $0.10.
    assert Decimal(json.loads(ledger.read_text())["reserved_usd"]) <= Decimal("0.20")
    assert not reserve(9)


def test_corrupt_or_unknown_budget_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / "budget.json"
    monkeypatch.setattr(settings, "agent_evaluation_budget_path", str(ledger))
    assert not reserve_agent_evaluation("unpriced-model", "", [], [], 100)
    ledger.write_text("not json")
    assert not reserve_agent_evaluation("claude-opus-5", "", [], [], 100)


def test_normal_traffic_does_not_consume_test_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_evaluation_budget_path", None)
    assert reserve_agent_evaluation("custom-model", "", [], [], 100)
