from decimal import Decimal

import httpx
import pytest

import app.llm.client as module
from app.llm.client import LLMClient
from app.llm.pricing import EvaluationBudget, estimate_cost


@pytest.mark.parametrize(
    "status,expected", [(401, 1), (403, 1), (400, 1), (404, 1), (429, 2), (503, 2)]
)
async def test_only_transient_failures_retry(
    monkeypatch: pytest.MonkeyPatch, status: int, expected: int
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared:
        monkeypatch.setattr(module, "_http_client", shared)
        client = LLMClient(api_key="test-only")
        client.max_retries = 1
        result = await client._call_chat_completions("system", "user")
    assert result[0] is None
    assert len(calls) == expected
    assert client.last_attempt_count == expected
    assert client.last_outcome != "success"


async def test_invalid_json_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "[1,2]"}}]}
            )
        )
    ) as shared:
        monkeypatch.setattr(module, "_http_client", shared)
        client = LLMClient(api_key="test-only")
        assert (await client._call_chat_completions("system", "user"))[0] is None
    assert client.last_attempt_count == 1
    assert client.last_outcome == "invalid_response"


def test_budget_rejects_unknown_price_and_over_limit() -> None:
    budget = EvaluationBudget(limit=Decimal("0.01"))
    assert not budget.reserve("unknown", "s", "u", 1)
    assert not budget.reserve("gpt-5.6-terra", "s", "u", 2000)
    assert budget.reserved == 0
    assert budget.reserve("gpt-5.6-luna", "s", "u", 100)
    assert budget.reserved > 0
    assert estimate_cost("unknown", 10, 10) is None


async def test_shutdown_closes_shared_client() -> None:
    await module.start_http_client()
    client = module._http_client
    await module.close_http_client()
    assert client is not None and client.is_closed
    assert module._http_client is None
