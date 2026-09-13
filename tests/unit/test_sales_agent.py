"""The sales agent loop, with a scripted model and fake tools -- no network, no money."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock

from app.core.config import settings
from app.services.sales_agent import AgentCart, SalesAgent, agent_available


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=100, output_tokens=20, cache_read_input_tokens=0, cache_creation_input_tokens=0
    )


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[BetaTextBlock(type="text", text=text)],
        usage=_usage(),
    )


def _tool(name: str, args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[BetaToolUseBlock(type="tool_use", id=f"tu_{name}", name=name, input=args)],
        usage=_usage(),
    )


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeTools:
    def __init__(self) -> None:
        self.ran: list[tuple[str, dict[str, Any]]] = []

    async def run(self, name: str, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        self.ran.append((name, args))
        return {"products": [{"id": 7, "name": "Fanera 12mm", "price_from_uzs": "150000"}]}


async def test_the_agent_uses_a_tool_then_answers() -> None:
    client = FakeClient(
        [_tool("search_products", {"query": "fanera"}), _text("Fanera 12mm bor, 150 000 so'm.")]
    )
    tools = FakeTools()
    cart = AgentCart()

    reply = await SalesAgent(None, tools, client=client).reply("fanera bormi?", "uz_latn", cart)

    assert reply == "Fanera 12mm bor, 150 000 so'm."
    assert tools.ran == [("search_products", {"query": "fanera"})]
    # The second call carries the tool result back.
    last = client.calls[1]["messages"][-1]["content"][0]
    assert last["type"] == "tool_result" and last["tool_use_id"] == "tu_search_products"
    assert client.calls[0]["model"] == settings.agent_model


async def test_only_plain_text_is_remembered() -> None:
    client = FakeClient([_tool("search_products", {"query": "x"}), _text("javob")])
    cart = AgentCart()
    await SalesAgent(None, FakeTools(), client=client).reply("salom", "ru", cart)

    assert cart.history == [
        {"role": "user", "content": "salom"},
        {"role": "assistant", "content": "javob"},
    ]


async def test_the_customer_language_reaches_the_model() -> None:
    client = FakeClient([_text("Здравствуйте")])
    await SalesAgent(None, FakeTools(), client=client).reply("salom", "ru", AgentCart())
    assert "Russian" in client.calls[0]["system"][1]["text"]


async def test_an_api_error_hands_over_to_the_old_flow() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    client = FakeClient([anthropic.APIConnectionError(request=request)])
    cart = AgentCart()
    assert (
        await SalesAgent(None, FakeTools(), client=client).reply("salom", "uz_latn", cart) is None
    )
    assert cart.history == []


async def test_a_refusal_hands_over_to_the_old_flow() -> None:
    refusal = SimpleNamespace(stop_reason="refusal", content=[], usage=_usage())
    client = FakeClient([refusal])
    assert (
        await SalesAgent(None, FakeTools(), client=client).reply("x", "uz_latn", AgentCart())
        is None
    )


async def test_a_runaway_tool_loop_stops() -> None:
    rounds = settings.agent_max_tool_rounds + 1
    client = FakeClient([_tool("search_products", {"query": "x"}) for _ in range(rounds)])
    assert (
        await SalesAgent(None, FakeTools(), client=client).reply("x", "uz_latn", AgentCart())
        is None
    )
    assert len(client.calls) == rounds


def test_the_agent_is_off_without_a_key() -> None:
    assert settings.anthropic_api_key == "placeholder_anthropic_key"
    assert agent_available() is False
