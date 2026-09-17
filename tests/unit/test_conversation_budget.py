"""Budget gates cover every attempt, including serialized tool rounds."""

from unittest.mock import patch

import anthropic

from app.core.config import settings
from app.services.sales_agent import AgentCart, SalesAgent
from tests.unit.test_sales_agent import FakeClient, FakeTools, _text, _tool


async def test_budget_refusal_prevents_provider_call():
    client = FakeClient([_text("never")])
    with patch("app.services.sales_agent.reserve_agent_evaluation", return_value=False) as reserve:
        assert await SalesAgent(None, FakeTools(), client).reply("hello", "ru", AgentCart()) is None
    assert reserve.call_count == 1
    assert client.calls == []


async def test_budget_reserved_for_full_serializable_tool_round():
    import json

    client = FakeClient([_tool("search_products", {"query": "fanera"}), _text("found")])
    payloads = []

    def reserve(model, system, messages, tools, max_output):
        payloads.append(json.loads(json.dumps([system, messages, tools])))
        return len(payloads) == 1

    with patch("app.services.sales_agent.reserve_agent_evaluation", side_effect=reserve):
        assert await SalesAgent(None, FakeTools(), client).reply("hello", "ru", AgentCart()) is None
    assert len(client.calls) == 1
    assert len(payloads) == 2
    assert payloads[1][1][-1]["content"][0]["type"] == "tool_result"
    assert payloads[1][2][0]["name"] == "get_knowledge"


async def test_evaluation_disables_sdk_retry_and_provider_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent_evaluation_budget_path", str(tmp_path / "ledger.json"))

    class EvaluationClient(FakeClient):
        def with_options(self, **kwargs):
            assert kwargs == {"max_retries": 0, "base_url": "https://api.anthropic.com"}
            return self

    client = EvaluationClient([_text("answer")])
    with patch("app.services.sales_agent.reserve_agent_evaluation", return_value=True):
        assert (
            await SalesAgent(None, FakeTools(), client).reply("hello", "ru", AgentCart())
            == "answer"
        )
    assert client.calls[0]["fallbacks"] is anthropic.omit
    assert client.calls[0]["betas"] is anthropic.omit
