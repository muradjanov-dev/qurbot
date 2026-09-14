import json
from decimal import Decimal

import httpx
import pytest

import app.llm.client as module
from app.llm.client import LLMClient
from app.llm.models import BatchLineInput, DisambiguationCandidateInput
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


async def test_anthropic_provider_uses_native_structured_messages_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": '{"reply":"Salom! 10 dona fanera 12mm"}'},
                ],
                "usage": {"input_tokens": 12, "output_tokens": 7},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared:
        monkeypatch.setattr(module, "_http_client", shared)
        client = LLMClient(
            api_key="anthropic-test-key",
            model="claude-opus-5",
            base_url="https://api.anthropic.com/v1",
            provider="anthropic",
        )
        reply = await client.guide_customer("salom")

    assert reply == "Salom! 10 dona fanera 12mm"
    assert len(requests) == 1
    request = requests[0]
    payload = json.loads(request.content)
    assert request.url == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "anthropic-test-key"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in request.headers
    assert payload["model"] == "claude-opus-5"
    assert payload["max_tokens"] > 0
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert payload["output_config"]["format"]["schema"]["required"] == ["reply"]
    assert payload["messages"][0]["role"] == "user"


async def test_anthropic_batch_disambiguation_has_a_strict_output_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"lines":[{"line_no":1,"canonical_id":9,'
                            '"confidence":0.95,"reason":"match","question":null,'
                            '"search_term":null}]}'
                        ),
                    }
                ],
                "usage": {"input_tokens": 40, "output_tokens": 20},
            },
        )

    line = BatchLineInput(
        line_no=1,
        raw_text="fanera",
        normalized_text="fanera",
        candidates=[DisambiguationCandidateInput(canonical_id=9, name_uz="Fanera")],
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared:
        monkeypatch.setattr(module, "_http_client", shared)
        client = LLMClient(
            api_key="anthropic-test-key",
            model="claude-opus-5",
            provider="anthropic",
        )
        result = await client.disambiguate_batch([line])

    assert result.lines[1].canonical_id == 9
    schema = payloads[0]["output_config"]["format"]["schema"]  # type: ignore[index]
    assert schema["required"] == ["lines"]  # type: ignore[index]
    item_schema = schema["properties"]["lines"]["items"]  # type: ignore[index]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == {
        "line_no",
        "canonical_id",
        "confidence",
        "reason",
        "question",
        "search_term",
    }


async def test_anthropic_single_disambiguation_has_a_strict_output_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": '{"canonical_id":9,"confidence":0.95,"reason":"match"}',
                    }
                ],
                "usage": {"input_tokens": 30, "output_tokens": 12},
            },
        )

    candidate = DisambiguationCandidateInput(canonical_id=9, name_uz="Fanera")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared:
        monkeypatch.setattr(module, "_http_client", shared)
        client = LLMClient(
            api_key="anthropic-test-key",
            model="claude-opus-5",
            provider="anthropic",
        )
        result = await client.disambiguate("fanera", "fanera", [candidate])

    assert result.canonical_id == 9
    schema = payloads[0]["output_config"]["format"]["schema"]  # type: ignore[index]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["canonical_id", "confidence", "reason"]


async def test_anthropic_whole_message_parse_has_a_strict_output_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"lines":[{"name":"Fanera","qty":"10.5","unit":"dona",'
                            '"confidence":0.95}]}'
                        ),
                    }
                ],
                "usage": {"input_tokens": 25, "output_tokens": 14},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as shared:
        monkeypatch.setattr(module, "_http_client", shared)
        client = LLMClient(
            api_key="anthropic-test-key",
            model="claude-opus-5",
            provider="anthropic",
        )
        result = await client.parse_whole_message("10 dona fanera")

    assert result.lines[0].name == "Fanera"
    assert result.lines[0].qty == Decimal("10.5")
    schema = payloads[0]["output_config"]["format"]["schema"]  # type: ignore[index]
    item_schema = schema["properties"]["lines"]["items"]  # type: ignore[index]
    assert item_schema["additionalProperties"] is False
    assert item_schema["properties"]["qty"]["type"] == "string"
    assert set(item_schema["required"]) == {"name", "qty", "unit", "confidence"}


def test_budget_rejects_unknown_price_and_over_limit() -> None:
    budget = EvaluationBudget(limit=Decimal("0.01"))
    assert not budget.reserve("unknown", "s", "u", 1)
    assert not budget.reserve("gpt-5.6-terra", "s", "u", 2000)
    assert budget.reserved == 0
    assert budget.reserve("gpt-5.6-luna", "s", "u", 100)
    assert budget.reserved > 0
    assert estimate_cost("unknown", 10, 10) is None


def test_claude_opus_5_list_price_is_accounted() -> None:
    assert estimate_cost("claude-opus-5", 1_000_000, 1_000_000) == Decimal("30.000000")


async def test_shutdown_closes_shared_client() -> None:
    await module.start_http_client()
    client = module._http_client
    await module.close_http_client()
    assert client is not None and client.is_closed
    assert module._http_client is None
