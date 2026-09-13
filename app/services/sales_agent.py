"""AI sales agent: Claude chats with the customer and drives the basket through tools.

The model only ever sees products our own catalogue search returns, and it never
places an order: `prepare_order` stores phone and address, and the customer
presses the existing confirm button, which runs the same `place_order` as before.

Only plain text turns are remembered between messages. Tool calls and results
live for one customer message, so a long chat does not re-send old search
results on every call.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol, cast

import anthropic
from anthropic.types.beta import (
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaToolUseBlock,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import llm_cost_usd_total
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.agent import parse_agent_qty, trim_history
from app.domain.normalize.phone import normalize_uz_phone
from app.domain.optimizer.models import BasketItemQuery
from app.domain.optimizer.serde import deserialize_variant, serialize_variant
from app.services.address_service import AddressService
from app.services.catalog_service import CatalogService
from app.services.quote_service import QuoteService

logger = get_logger(__name__)

_PLACEHOLDER_KEYS = frozenset({"", "changeme", "placeholder_anthropic_key"})
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_LANGUAGES = {
    "uz_latn": "Uzbek, Latin script",
    "uz_cyrl": "Uzbek, Cyrillic script",
    "ru": "Russian",
}

SYSTEM_PROMPT = """You are QurBot, a sales assistant in a Telegram chat. QurBot sells \
construction materials (plywood, boards, timber, fasteners) and delivers them.

Rules:
- Offer only products returned by search_products. Never invent products, prices or stock.
- Help step by step: understand what is needed, search, confirm the exact product and \
quantity with the customer, then set_basket_item.
- When the basket is ready, call get_quote and tell the customer the total.
- To order you need a phone number and a delivery address. Offer the saved addresses \
(get_saved_addresses); the customer may also type an address or send a location pin.
- Then call prepare_order. A confirm button appears under your message; ask the customer \
to press it. Never say the order is placed.
- If a product is not found, say so briefly and give the support phone.
- Write short, friendly plain text. No markdown."""

TOOLS: list[BetaToolParam] = [
    {
        "name": "search_products",
        "description": "Search the catalogue for products shops sell. Returns id, name, price.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "e.g. 'fanera 12mm'"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_basket_item",
        "description": "Set the quantity of one product in the basket. qty 0 removes it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "qty": {"type": "number"},
            },
            "required": ["product_id", "qty"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_quote",
        "description": "Price the current basket with delivery. Returns lines and totals.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_saved_addresses",
        "description": "The customer's saved delivery addresses.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prepare_order",
        "description": "Store contact details and show the customer the confirm button.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "address": {"type": "string"},
                "comment": {"type": "string"},
            },
            "required": ["phone", "address"],
            "additionalProperties": False,
        },
    },
]


@dataclass
class AgentCart:
    """What the agent keeps between customer messages (stored in FSM data)."""

    history: list[dict[str, str]] = field(default_factory=list)
    basket: list[dict[str, str | int]] = field(default_factory=list)
    quote: dict[str, Any] | None = None
    order: dict[str, str | None] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AgentCart:
        data = data or {}
        return cls(
            history=list(data.get("history", [])),
            basket=list(data.get("basket", [])),
            quote=data.get("quote"),
            order=data.get("order"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "history": self.history,
            "basket": self.basket,
            "quote": self.quote,
            "order": self.order,
        }


class AgentTools(Protocol):
    async def run(self, name: str, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]: ...


def agent_available() -> bool:
    return settings.agent_enabled and settings.anthropic_api_key not in _PLACEHOLDER_KEYS


class DbAgentTools:
    """The tools, backed by the same services the button flow uses."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        self.session = session
        self.user = user

    async def run(self, name: str, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        if name == "search_products":
            return await self._search(str(args.get("query", "")))
        if name == "set_basket_item":
            return await self._set_item(args, cart)
        if name == "get_quote":
            return await self._quote(cart)
        if name == "get_saved_addresses":
            addresses = await AddressService(self.session).list_for(self.user)
            return {"addresses": [a.address_text for a in addresses]}
        if name == "prepare_order":
            return self._prepare_order(args, cart)
        return {"error": f"unknown tool {name}"}

    async def _search(self, query: str) -> dict[str, Any]:
        if not query.strip():
            return {"error": "empty query"}
        catalog = CatalogService(CatalogRepository(self.session), OpsRepository(self.session))
        found = await catalog.find_for_customer(query, limit=settings.agent_search_limit)
        offers = await ShopRepository(self.session).get_active_offers_for_canonicals(
            [c.canonical_id for c in found]
        )
        cheapest: dict[int, tuple[Decimal, str]] = {}
        for offer in offers:
            if offer.canonical_id is None or offer.canonical_id in cheapest:
                continue
            cheapest[offer.canonical_id] = (offer.price_per_pack, offer.pack_unit_code or "")
        products = []
        for cand in found:
            price = cheapest.get(cand.canonical_id)
            products.append(
                {
                    "id": cand.canonical_id,
                    "name": cand.name_uz,
                    "price_from_uzs": f"{price[0]:.0f}" if price else None,
                    "unit": price[1] if price else None,
                }
            )
        return {"products": products}

    async def _set_item(self, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        qty = parse_agent_qty(args.get("qty"), max_qty=Decimal(settings.basket_max_qty))
        if qty is None:
            return {"error": "invalid quantity"}
        try:
            product_id = int(args.get("product_id", 0))
        except (TypeError, ValueError):
            return {"error": "invalid product_id"}
        product = await CatalogRepository(self.session).get(product_id)
        if product is None:
            return {"error": "product not found"}

        cart.basket = [line for line in cart.basket if line["canonical_id"] != product_id]
        if qty > 0:
            cart.basket.append(
                {
                    "canonical_id": product_id,
                    "name": product.name_uz,
                    "qty": str(qty),
                    "unit_code": product.base_unit_code,
                }
            )
        # The basket changed, so any earlier price and order are stale.
        cart.quote = None
        cart.order = None
        return {"basket": cart.basket}

    async def _quote(self, cart: AgentCart) -> dict[str, Any]:
        if not cart.basket:
            return {"error": "basket is empty"}
        items = [
            BasketItemQuery(
                line_no=index,
                canonical_id=int(line["canonical_id"]),
                name_uz=str(line["name"]),
                needed_qty=Decimal(str(line["qty"])),
                unit_code=str(line["unit_code"]),
            )
            for index, line in enumerate(cart.basket, start=1)
        ]
        service = QuoteService(ShopRepository(self.session), CatalogRepository(self.session))
        result = await service.optimize_basket(items, district_id=self.user.district_id)
        if not result.deduplicated_variants:
            cart.quote = None
            return {"orderable": False, "missing": [i.name_uz for i in items]}
        variant = result.deduplicated_variants[0]
        cart.quote = serialize_variant(variant)
        return {
            "orderable": variant.is_orderable,
            "lines": [
                {
                    "name": line.product_name,
                    "qty": f"{line.billed_qty.normalize():f}",
                    "unit": line.pack_unit,
                    "cost_uzs": f"{line.line_cost_uzs:.0f}",
                }
                for group in variant.shop_groups
                for line in group.lines
            ],
            "items_total_uzs": f"{variant.items_total_uzs:.0f}",
            "delivery_uzs": f"{variant.delivery_total_uzs:.0f}",
            "grand_total_uzs": f"{variant.grand_total_uzs:.0f}",
            "missing": [item.name_uz for item in variant.missing_lines],
        }

    def _prepare_order(self, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        if cart.quote is None or not deserialize_variant(cart.quote).is_orderable:
            return {"error": "call get_quote first; the basket must be orderable"}
        phone = normalize_uz_phone(str(args.get("phone", "")))
        if phone is None:
            return {"error": "invalid Uzbek phone number"}
        address = str(args.get("address", "")).strip()
        if len(address) < settings.min_delivery_address_length:
            return {"error": "address too short, ask for street and house"}
        comment = str(args.get("comment") or "").strip() or None
        cart.order = {"phone": phone, "address": address, "comment": comment}
        return {"ok": True, "confirm_button_shown": True}


class SalesAgent:
    def __init__(
        self,
        session: AsyncSession | None,
        tools: AgentTools,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.session = session
        self.tools = tools
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=settings.agent_timeout_seconds
        )

    async def reply(self, text: str, lang: str, cart: AgentCart) -> str | None:
        """Answer one customer message. None means: let the old flow answer."""
        if not await self._has_budget():
            logger.warning("agent_token_budget_exceeded")
            return None

        history = trim_history(cart.history, settings.agent_history_max_messages - 1)
        language = _LANGUAGES.get(lang, _LANGUAGES["uz_latn"])
        system: list[BetaTextBlockParam] = [
            {"type": "text", "text": SYSTEM_PROMPT},
            {
                "type": "text",
                "text": f"Reply in {language}. Support phone: {settings.support_phone}.",
            },
        ]
        messages = cast(list[BetaMessageParam], [*history, {"role": "user", "content": text}])

        answer: str | None = None
        for _ in range(settings.agent_max_tool_rounds + 1):
            started = time.monotonic()
            try:
                response = await self.client.beta.messages.create(
                    model=settings.agent_model,
                    max_tokens=settings.agent_max_tokens,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                    output_config={"effort": settings.agent_effort},
                    cache_control={"type": "ephemeral"},
                    betas=[_FALLBACK_BETA],
                    fallbacks="default",
                )
            except anthropic.APIError as exc:
                logger.warning("agent_call_failed", error=str(exc))
                return None
            await self._record(text, response, int((time.monotonic() - started) * 1000))

            if response.stop_reason == "refusal":
                return None
            if response.stop_reason != "tool_use":
                answer = "".join(
                    b.text for b in response.content if isinstance(b, BetaTextBlock)
                ).strip()
                break

            messages.append({"role": "assistant", "content": response.content})
            results: list[BetaToolResultBlockParam] = []
            for block in response.content:
                if not isinstance(block, BetaToolUseBlock):
                    continue
                output = await self.tools.run(block.name, dict(block.input), cart)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, ensure_ascii=False),
                        "is_error": "error" in output,
                    }
                )
            messages.append({"role": "user", "content": results})

        if not answer:
            return None
        cart.history = [
            *history,
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ]
        return answer

    async def _has_budget(self) -> bool:
        if self.session is None:
            return True
        since = datetime.now(UTC) - timedelta(hours=24)
        used = await OpsRepository(self.session).get_llm_tokens_since(since)
        return used < settings.llm_daily_token_budget

    async def _record(self, text: str, response: Any, latency_ms: int) -> None:
        usage = response.usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        input_price = settings.agent_input_usd_per_mtok
        cost = (
            Decimal(usage.input_tokens) * input_price
            + Decimal(cache_read) * input_price * settings.agent_cache_read_price_ratio
            + Decimal(cache_write) * input_price * settings.agent_cache_write_price_ratio
            + Decimal(usage.output_tokens) * settings.agent_output_usd_per_mtok
        ) / Decimal(1_000_000)
        cost = cost.quantize(Decimal("0.000001"))
        llm_cost_usd_total.inc(float(cost))
        if self.session is None:
            return
        await OpsRepository(self.session).record_llm_call(
            purpose="sales_agent",
            prompt_version=settings.llm_prompt_version,
            input_hash=hashlib.sha256(text.encode()).hexdigest(),
            input_tokens=usage.input_tokens + cache_read + cache_write,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=bool(usage.cache_read_input_tokens),
        )
