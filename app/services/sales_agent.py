"""AI sales agent: Claude chats with the customer and drives the basket through tools.

The model only ever sees products our own catalogue search returns, and it never
places an order: `prepare_order` stores phone and address, and the customer
presses the existing confirm button, which runs the same `place_order` as before.

Only plain text turns are remembered between messages. Tool calls and results
live for one customer message, so a long chat does not re-send old search
results on every call.
"""

from __future__ import annotations

import asyncio
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import localized_name
from app.core.config import settings
from app.core.i18n import DEFAULT_LANG
from app.core.logging import get_logger
from app.core.metrics import llm_cost_usd_total
from app.db.models.catalog import CanonicalProduct
from app.db.models.shop import District, Shop, ShopDeliveryRule
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.agent import parse_agent_qty, trim_history
from app.domain.matching.models import CandidateMatch
from app.domain.normalize.phone import normalize_uz_phone
from app.domain.normalize.text import normalize_query
from app.domain.optimizer.models import BasketItemQuery
from app.domain.optimizer.serde import deserialize_variant, serialize_variant
from app.domain.pricing.units import STANDARD_UNITS
from app.llm.evaluation import reserve_agent_evaluation
from app.llm.pricing import RATES
from app.services.address_service import AddressService
from app.services.cart_service import CartConflict, InvalidCartItem
from app.services.catalog_service import CatalogService
from app.services.quote_service import QuoteService

logger = get_logger(__name__)

_PLACEHOLDER_KEYS = frozenset({"", "changeme", "placeholder_anthropic_key"})
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# The sample matters more than the label. Told only "Uzbek, Cyrillic script",
# the model kept answering a Cyrillic customer in Latin -- both are Uzbek, so
# the instruction read as satisfied. Showing the script settles it.
_LANGUAGES = {
    "uz_latn": ("Uzbek written in the Latin alphabet", "Kechirasiz, bu mahsulot topilmadi."),
    "uz_cyrl": (
        "Uzbek written in the Cyrillic alphabet",
        "Кечирасиз, бу маҳсулот топилмади.",
    ),
    "ru": ("Russian", "Извините, этот товар не найден."),
}

SYSTEM_PROMPT = """You are QurBot, a sales assistant in a Telegram chat. QurBot sells \
construction materials (plywood, boards, timber, fasteners) and delivers them.

You are not an FAQ. You take the customer all the way from "I need something" to a
finished order, doing the work yourself instead of telling them which button to press.
Drive the conversation: at every point either you are asking the one thing you still
need, or you are calling the tool that gets you the next thing.

The path, in order:

1. UNDERSTAND. Work out what they are building and which material that needs. Ask one
   short question at a time when purpose or dimensions are missing -- never a list of
   questions.
2. FIND. Call search_products. Offer only what it returns, at most three at a time, in
   the order returned. Never invent a product, a price or stock. If nothing fits, say so
   plainly and give the support phone.
3. CONFIRM. Name the exact product, its unit and the quantity, and get a yes.
4. ADD. Call set_basket_item yourself as soon as they agree -- do not ask them to add it.
   The quantity you set replaces the line; it never adds twice. Then say what is in the
   basket now and ask whether they need anything else.
5. DESTINATION. Before any total, you need a district. Use the one already chosen if
   get_delivery_options reports one. Otherwise call get_delivery_options for the regions,
   ask which region, call it again for that region's districts, ask which district, then
   call set_delivery_district with its id. Never guess an id.
6. PRICE. Call get_quote. Give the total only when every line is orderable.
7. DETAILS. Ask for the phone number, then the street address. Offer saved addresses first
   (get_saved_addresses). Ask for these only when an order is actually being placed.
8. CONFIRM BUTTON. Call prepare_order. A confirm button appears under your message. Ask
   them to press it. You never place the order yourself, and you never say it is placed,
   paid or reserved.

When a price is unknown (get_quote answers operator_confirmation_required, or a product
is marked price on request or unverified stock):

- Say honestly that this item has to be priced by an operator. Never invent a price, and
  never present a partial sum of the known lines as the total.
- Offer to send the enquiry for them. If they agree, collect name, phone, district and
  address the same way as above, then call submit_sales_request yourself. Do not send
  them to a button to do it.
- An enquiry is not an order: nothing is sold, charged or reserved, and an operator
  replies in this chat. Say that. After submitting, say the request number and stop --
  the conversation is with an operator now.

Also:
- Answer the customer's latest message. Earlier turns are background for what they
  mean now, not a queue to work through: if they asked about bricks and then about
  boards, they are asking about boards. Do not open a reply by reporting on an older
  question they have moved on from.
- Offer a human operator for anything you cannot answer, but never claim to have
  connected one; the customer presses the operator button themselves.
- Never ask for a phone number just to chat or to answer a question.
- Call get_knowledge for delivery and support policy rather than stating it from memory.
- Write short, friendly plain text. No markdown."""

TOOLS: list[BetaToolParam] = [
    {
        "name": "get_knowledge",
        "description": "Get configured support contacts and delivery rules. Never invent policy.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
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
                "unit_code": {
                    "type": "string",
                    "description": "Requested unit, e.g. kg, dona, qop.",
                },
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
        "name": "get_delivery_options",
        "description": (
            "Where we deliver. With no region, lists the regions; with a region, lists that "
            "region's districts with their ids. Also reports the district already chosen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region name exactly as returned, e.g. 'Toshkent'.",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "set_delivery_district",
        "description": (
            "Set where this order is going. Required before a quote can include delivery. "
            "Use an id from get_delivery_options; never guess one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"district_id": {"type": "integer"}},
            "required": ["district_id"],
            "additionalProperties": False,
        },
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
    {
        "name": "submit_sales_request",
        "description": (
            "Send the whole basket to an operator as a manual enquiry, for when a product has "
            "no confirmed price or stock. This is NOT an order: nothing is sold, charged or "
            "reserved. An operator works out the price and comes back to the customer. "
            "Only call it after the customer has agreed and given all four details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "district_id": {"type": "integer"},
                "address": {"type": "string"},
            },
            "required": ["name", "phone", "district_id", "address"],
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
    revision: int | None = None
    quote_revision: int | None = None
    # Where this basket is going. Separate from users.district_id because a
    # customer may order to a site that is not their saved district, and a
    # guest has no saved district at all -- without it the agent could not
    # price delivery and had no way to ask.
    district_id: int | None = None
    # Messages at or below this sequence are not the assistant's to answer.
    # Set when it rejoins a conversation a human was holding: the customer's
    # unanswered backlog is context at most, and replaying it made the agent
    # answer a question about bricks when the customer had just asked about
    # boards.
    history_from: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AgentCart:
        data = data or {}
        return cls(
            history=list(data.get("history", [])),
            basket=list(data.get("basket", [])),
            quote=data.get("quote"),
            order=data.get("order"),
            revision=data.get("revision"),
            quote_revision=data.get("quote_revision"),
            district_id=data.get("district_id"),
            history_from=int(data.get("history_from") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "history": self.history,
            "basket": self.basket,
            "quote": self.quote,
            "order": self.order,
            "revision": self.revision,
            "quote_revision": self.quote_revision,
            "district_id": self.district_id,
            "history_from": self.history_from,
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
        if name == "get_knowledge":
            rules = (
                await self.session.scalars(
                    select(ShopDeliveryRule)
                    .join(Shop)
                    .where(
                        Shop.name == settings.house_shop_name,
                        Shop.is_active.is_(True),
                    )
                )
            ).all()
            return {
                "support_phones": settings.support_phones,
                "delivery_eta_min_hours": settings.delivery_eta_min_hours,
                "delivery_eta_max_hours": settings.delivery_eta_max_hours,
                "delivery_rules": [
                    {
                        "district_id": rule.district_id,
                        "fee_uzs": str(rule.fee),
                        "free_above_uzs": str(rule.free_above)
                        if rule.free_above is not None
                        else None,
                        "min_order_uzs": str(rule.min_order),
                        "eta_hours": rule.eta_hours,
                        "pickup_only": rule.is_pickup_only,
                    }
                    for rule in rules
                ],
                "reference": "configured_support_and_shop_delivery_rules",
            }
        if name == "search_products":
            return await self._search(str(args.get("query", "")))
        if name == "set_basket_item":
            return await self._set_item(args, cart)
        if name == "get_quote":
            return await self._quote(cart)
        if name == "get_saved_addresses":
            addresses = await AddressService(self.session).list_for(self.user)
            return {"addresses": [a.address_text for a in addresses]}
        if name == "get_delivery_options":
            return await self._delivery_options(args, cart)
        if name == "set_delivery_district":
            return await self._set_district(args, cart)
        if name == "prepare_order":
            return self._prepare_order(args, cart)
        if name == "submit_sales_request":
            return await self._submit_request(args, cart)
        return {"error": f"unknown tool {name}"}

    def _district_id(self, cart: AgentCart) -> int | None:
        """What this basket is being delivered to, chosen over the saved default."""
        return cart.district_id if cart.district_id is not None else self.user.district_id

    async def _delivery_options(self, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        shops = ShopRepository(self.session)
        chosen_id = self._district_id(cart)
        chosen = await self.session.get(District, chosen_id) if chosen_id else None
        current = (
            {
                "district_id": chosen.id,
                "district": localized_name(chosen.name_uz, chosen.name_ru, self.user.lang),
                "region": chosen.region,
            }
            if chosen
            else None
        )
        region = str(args.get("region") or "").strip()
        if not region:
            return {
                "regions": list(await shops.list_regions()),
                "current": current,
                "next_step": "Ask which region, then call this again with that region.",
            }
        districts = await shops.list_districts(region)
        if not districts:
            return {
                "error": "unknown region",
                "regions": list(await shops.list_regions()),
            }
        return {
            "region": region,
            "districts": [
                {
                    "id": row.id,
                    "name": localized_name(row.name_uz, row.name_ru, self.user.lang),
                }
                for row in districts
            ],
            "current": current,
        }

    async def _set_district(self, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        try:
            district_id = int(args["district_id"])
        except (KeyError, TypeError, ValueError):
            return {"error": "district_id must be an id from get_delivery_options"}
        district = await self.session.get(District, district_id)
        if district is None:
            return {"error": "no such district; call get_delivery_options"}
        # Delivery is priced per district, so an existing quote is stale the
        # moment the destination moves.
        if cart.district_id != district_id:
            cart.quote = None
            cart.order = None
        cart.district_id = district_id
        return {
            "ok": True,
            "district": localized_name(district.name_uz, district.name_ru, self.user.lang),
            "region": district.region,
        }

    async def _submit_request(self, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        """Hand the basket to an operator as a priced-by-hand enquiry.

        Deliberately separate from `prepare_order`: an enquiry sells nothing,
        so it needs no quote and no confirm button, and the customer must not
        be told it is an order.
        """
        from app.services.sales_request_service import SalesRequestService

        if not cart.basket:
            return {"error": "basket is empty"}
        try:
            district_id = int(args["district_id"])
        except (KeyError, TypeError, ValueError):
            return {"error": "district_id must be an id from get_delivery_options"}
        try:
            row = await SalesRequestService(self.session).create(
                self.user,
                revision=cart.revision if cart.revision is not None else -1,
                key=f"agent:{self.user.id}:{cart.revision}:{district_id}",
                name=str(args.get("name", "")),
                phone=str(args.get("phone", "")),
                district_id=district_id,
                address=str(args.get("address", "")),
                channel="telegram" if self.user.tg_id is not None else "web",
            )
        except CartConflict:
            return {"error": "the basket changed; call get_quote again and re-confirm"}
        except InvalidCartItem as exc:
            return {"error": f"cannot submit: {exc.message}"}
        # The enquiry hands the conversation to an operator, so this must be
        # the last tool of the turn.
        cart.quote = None
        cart.order = None
        return {
            "ok": True,
            "request_id": row.id,
            "handed_to_operator": True,
            "tell_customer": "An operator will work out the price and reply here.",
        }

    async def _search(self, query: str) -> dict[str, Any]:
        if not query.strip():
            return {"error": "empty query"}
        catalog = CatalogService(CatalogRepository(self.session), OpsRepository(self.session))
        found = await catalog.find_for_customer(query, limit=settings.agent_search_limit)
        catalogue_rows = await CatalogRepository(self.session).search_canonical_products(
            normalize_query(query).text_norm,
            limit=settings.agent_search_limit,
            require_offers=False,
        )
        seen = {candidate.canonical_id for candidate in found}
        for product in catalogue_rows:
            if product.id not in seen:
                found.append(
                    CandidateMatch(
                        canonical_id=product.id,
                        slug=product.slug,
                        name_uz=product.name_uz,
                        attributes=product.attributes,
                    )
                )
        found = found[: settings.agent_search_limit]
        product_rows = (
            await self.session.scalars(
                select(CanonicalProduct).where(
                    CanonicalProduct.id.in_([candidate.canonical_id for candidate in found]),
                )
            )
        ).all()
        by_id = {product.id: product for product in product_rows}
        offers = await ShopRepository(self.session).get_active_offers_for_canonicals(
            [c.canonical_id for c in found]
        )
        cheapest: dict[int, tuple[Decimal, str, Decimal, int]] = {}
        for offer in offers:
            if offer.canonical_id is None:
                continue
            previous = cheapest.get(offer.canonical_id)
            if previous is None or offer.price_per_pack < previous[0]:
                cheapest[offer.canonical_id] = (
                    offer.price_per_pack,
                    offer.pack_unit_code or "",
                    offer.pack_size,
                    offer.id,
                )
        products = []
        for cand in found:
            price = cheapest.get(cand.canonical_id)
            product = by_id[cand.canonical_id]
            needs_confirmation = bool(
                product.attributes.get("price_on_request")
                or product.attributes.get("stock_unverified")
            )
            if needs_confirmation or (price and price[0] <= 0):
                price = None
            products.append(
                {
                    "id": cand.canonical_id,
                    # The card is read by the customer, so it follows their
                    # script; the match itself is done on the Latin name.
                    "name": localized_name(
                        product.name_uz,
                        product.name_ru,
                        self.user.lang,
                        name_uz_cyrl=product.name_uz_cyrl,
                    ),
                    "price_from_uzs": f"{price[0]:.0f}" if price else None,
                    "unit": (f"{price[2]:f} {price[1]}" if price[2] != 1 else price[1])
                    if price
                    else None,
                    "pack_size": str(price[2]) if price else None,
                    "price_unit_code": price[1] if price else None,
                    "offer_id": price[3] if price else None,
                    "reference": f"/product/{cand.canonical_id}",
                    "unit_code": product.base_unit_code,
                    "price_on_request": price is None,
                    "stock_unverified": bool(product.attributes.get("stock_unverified"))
                    or price is None,
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

        existing = next((line for line in cart.basket if line["canonical_id"] == product_id), None)
        unit = str(
            args.get("unit_code") or (existing["unit_code"] if existing else product.base_unit_code)
        )
        if unit not in STANDARD_UNITS:
            return {"error": "invalid unit"}

        cart.basket = [line for line in cart.basket if line["canonical_id"] != product_id]
        if qty > 0:
            cart.basket.append(
                {
                    "canonical_id": product_id,
                    "name": product.name_uz,
                    "qty": str(qty),
                    "unit_code": unit,
                }
            )
        # The basket changed, so any earlier price and order are stale.
        cart.quote = None
        cart.order = None
        return {"basket": cart.basket}

    async def _quote(self, cart: AgentCart) -> dict[str, Any]:
        if not cart.basket:
            return {"error": "basket is empty"}
        products = (
            await self.session.scalars(
                select(CanonicalProduct).where(
                    CanonicalProduct.id.in_([int(line["canonical_id"]) for line in cart.basket]),
                )
            )
        ).all()
        if any(
            product.attributes.get("price_on_request") or product.attributes.get("stock_unverified")
            for product in products
        ):
            cart.quote = None
            cart.order = None
            return {"error": "operator_confirmation_required"}
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
        result = await service.optimize_basket(items, district_id=self._district_id(cart))
        if not result.deduplicated_variants:
            cart.quote = None
            return {"orderable": False, "missing": [i.name_uz for i in items]}
        variant = result.deduplicated_variants[0]
        if variant.missing_lines or not variant.is_orderable:
            cart.quote = None
            cart.order = None
            return {"error": "operator_confirmation_required"}
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
        if (
            cart.quote is None
            or not deserialize_variant(cart.quote).is_orderable
            or deserialize_variant(cart.quote).missing_lines
        ):
            return {"error": "call get_quote first; the basket must be orderable"}
        phone = normalize_uz_phone(str(args.get("phone", "")))
        if phone is None:
            return {"error": "invalid Uzbek phone number"}
        address = str(args.get("address", "")).strip()
        if len(address) < settings.min_delivery_address_length:
            return {"error": "address too short, ask for street and house"}
        district_id = self._district_id(cart)
        if district_id is None:
            return {"error": "no delivery district; call get_delivery_options first"}
        comment = str(args.get("comment") or "").strip() or None
        cart.order = {
            "phone": phone,
            "address": address,
            "comment": comment,
            # Carried onto the confirm step so the order is re-priced for the
            # district the customer actually chose, not their saved default.
            "district_id": str(district_id),
        }
        return {"ok": True, "confirm_button_shown": True}


class SalesAgent:
    channel_instructions: str = ""

    def __init__(
        self,
        session: AsyncSession | None,
        tools: AgentTools,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.session = session
        self.tools = tools
        self.last_error: str | None = None
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=(
                "https://api.anthropic.com"
                if settings.agent_evaluation_budget_path is not None
                else settings.anthropic_base_url.rstrip("/").removesuffix("/v1")
            ),
            timeout=settings.agent_timeout_seconds,
            max_retries=0 if settings.agent_evaluation_budget_path is not None else 2,
        )

    async def reply(self, text: str, lang: str, cart: AgentCart) -> str | None:
        """Answer one customer message. None means: let the old flow answer."""
        if not await self._has_budget():
            self.last_error = "daily_budget"
            logger.warning("agent_token_budget_exceeded")
            return None

        history = trim_history(cart.history, settings.agent_history_max_messages - 1)
        language, sample = _LANGUAGES.get(lang, _LANGUAGES[DEFAULT_LANG])
        phones = ", ".join(settings.support_phones)
        system: list[BetaTextBlockParam] = [
            {"type": "text", "text": SYSTEM_PROMPT},
            {
                "type": "text",
                "text": (
                    f"Write every reply in {language}, with no exceptions. "
                    f'A reply in this style is correct: "{sample}" '
                    "Use that alphabet for the whole message, including product "
                    "names you repeat back from search results. Never switch "
                    "alphabet mid-message and never answer in another language, "
                    "even if the customer writes in one. "
                    f"Support phone: {phones}."
                )
                + getattr(self, "channel_instructions", ""),
            },
        ]
        messages = cast(list[BetaMessageParam], [*history, {"role": "user", "content": text}])

        answer: str | None = None
        for _ in range(settings.agent_max_tool_rounds + 1):
            if not await asyncio.to_thread(
                reserve_agent_evaluation,
                settings.agent_model,
                system,
                messages,
                TOOLS,
                settings.agent_max_tokens,
            ):
                self.last_error = "evaluation_budget"
                return None
            started = time.monotonic()
            try:
                client = self.client
                if settings.agent_evaluation_budget_path is not None:
                    client = client.with_options(
                        max_retries=0, base_url="https://api.anthropic.com"
                    )
                response = await client.beta.messages.create(
                    model=settings.agent_model,
                    max_tokens=settings.agent_max_tokens,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                    output_config={"effort": settings.agent_effort},
                    cache_control={"type": "ephemeral"},
                    betas=[_FALLBACK_BETA]
                    if settings.agent_evaluation_budget_path is None
                    else anthropic.omit,
                    fallbacks="default"
                    if settings.agent_evaluation_budget_path is None
                    else anthropic.omit,
                )
            except anthropic.APIError as exc:
                self.last_error = (
                    "provider_timeout"
                    if isinstance(exc, anthropic.APITimeoutError)
                    else "provider_error"
                )
                logger.warning("agent_call_failed", cause=self.last_error)
                return None
            await self._record(text, response, int((time.monotonic() - started) * 1000))

            if response.stop_reason == "refusal":
                self.last_error = "refusal"
                return None
            if response.stop_reason != "tool_use":
                answer = "".join(
                    b.text for b in response.content if isinstance(b, BetaTextBlock)
                ).strip()
                break

            messages.append(
                cast(
                    BetaMessageParam,
                    {"role": "assistant", "content": [b.model_dump() for b in response.content]},
                )
            )
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
            self.last_error = "empty_or_tool_limit"
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
        # A refusal fallback may answer on another model; bill what actually ran.
        model = str(getattr(response, "model", None) or settings.agent_model)
        input_price, output_price = RATES.get(model, RATES[settings.agent_model])
        cost = (
            Decimal(usage.input_tokens) * input_price
            + Decimal(cache_read) * input_price * settings.agent_cache_read_price_ratio
            + Decimal(cache_write) * input_price * settings.agent_cache_write_price_ratio
            + Decimal(usage.output_tokens) * output_price
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
            # Prompt-cache reads are still billed; cache_hit marks free replays.
            cache_hit=False,
            model=model,
            outcome=str(response.stop_reason),
        )
