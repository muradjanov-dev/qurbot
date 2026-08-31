"""Basket and quote work shared by the storefront's pages and JSON endpoints.

The browser holds the basket (it is the customer's own scratch list, and it
should survive a reload without an account), but it is never believed. Every
line that comes back is re-read against the catalogue here, and every price is
computed server-side from live offers -- the client sends *what* was wanted,
never *what it costs*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_catalog_price, format_qty, format_uzs
from app.core.config import settings
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.optimizer.models import (
    BasketItemQuery,
    OptimizationStrategy,
    QuoteVariant,
)
from app.domain.parsing.parser import is_qty_orderable
from app.services.catalog_service import CatalogService
from app.services.quote_service import QuoteService

# What each optimizer strategy is called on a customer-facing card.
STRATEGY_LABEL_KEYS: dict[OptimizationStrategy, str] = {
    OptimizationStrategy.CHEAPEST_TOTAL: "web_quote_cheapest",
    OptimizationStrategy.SINGLE_SHOP: "web_quote_single_shop",
    OptimizationStrategy.FASTEST: "web_quote_fastest",
    OptimizationStrategy.PREMIUM: "web_quote_premium",
    OptimizationStrategy.BALANCED: "web_quote_balanced",
}

# Line states the browser renders, mapped from the matcher's decision.
STATUS_OK = "ok"
STATUS_CHOOSE = "choose"
STATUS_UNKNOWN = "unknown"

_MAX_BASKET_LINES = 60


@dataclass(frozen=True, slots=True)
class ValidatedBasket:
    """Client-supplied lines after they have been checked against the catalogue."""

    items: tuple[BasketItemQuery, ...]
    rejected: tuple[int, ...]


def _decode_qty(raw: object) -> Decimal | None:
    """Read a quantity the browser sent, refusing anything unorderable."""
    if isinstance(raw, bool):
        return None
    try:
        qty = Decimal(str(raw).strip().replace(",", "."))
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not is_qty_orderable(qty, max_qty=Decimal(settings.basket_max_qty)):
        return None
    return qty


def line_for_product(product: CanonicalProduct, qty: Decimal, line_no: int) -> dict[str, Any]:
    """A basket line for a product picked straight out of the catalogue.

    Same shape the parser produces, so a browsed product and a typed one flow
    through the rest of the basket identically.
    """
    return {
        "line_no": line_no,
        "raw_text": f"{format_qty(qty)} {product.base_unit_code} {product.name_uz}",
        "parsed_name": product.name_uz,
        "qty": str(qty),
        "unit_code": product.base_unit_code,
        "status": STATUS_OK,
        "canonical_id": product.id,
        "canonical_name": product.name_uz,
        "candidates": [],
    }


async def parse_basket_text(
    session: AsyncSession,
    raw_text: str,
    *,
    start_no: int = 0,
    user_id: int | None = None,
    lang: str = "uz_latn",
) -> list[dict[str, Any]]:
    """Run the free-text list through the same parse+match cascade the bot uses."""
    catalog_service = CatalogService(CatalogRepository(session), OpsRepository(session))
    results = await catalog_service.parse_and_match_basket(
        raw_text, user_id=user_id, require_offers=True
    )

    lines: list[dict[str, Any]] = []
    for offset, (parsed, decision) in enumerate(results, start=1):
        if decision.status == "auto_accept" and decision.canonical_id:
            status = STATUS_OK
        elif decision.status == "ask_user" and decision.candidates:
            status = STATUS_CHOOSE
        else:
            status = STATUS_UNKNOWN

        candidates = [
            {
                "canonical_id": candidate.canonical_id,
                "name": candidate.name_uz,
                "price": None,
            }
            for candidate in decision.candidates[:3]
        ]
        lines.append(
            {
                "line_no": start_no + offset,
                "raw_text": parsed.raw_text,
                "parsed_name": parsed.parsed_name,
                "qty": str(parsed.qty),
                "unit_code": parsed.unit_code or "dona",
                "status": status,
                "reason": "qty" if decision.method == "invalid_qty" else None,
                "canonical_id": decision.canonical_id if status == STATUS_OK else None,
                "canonical_name": (
                    decision.candidates[0].name_uz if decision.candidates else parsed.parsed_name
                ),
                "candidates": candidates,
            }
        )

    await _attach_candidate_prices(session, lines, lang=lang)
    return lines


async def _attach_candidate_prices(
    session: AsyncSession,
    lines: list[dict[str, Any]],
    *,
    lang: str,
) -> None:
    """Price the options on an ambiguous line, so they can be told apart.

    Two products with near-identical names are indistinguishable by name alone;
    the price is usually what tells the customer which one they meant.
    """
    canonical_ids = {
        candidate["canonical_id"]
        for line in lines
        if line["status"] == STATUS_CHOOSE
        for candidate in line["candidates"]
    }
    if not canonical_ids:
        return

    cheapest = await cheapest_prices(session, list(canonical_ids))
    reference = await _reference_prices(session, list(canonical_ids))
    for line in lines:
        if line["status"] != STATUS_CHOOSE:
            continue
        for candidate in line["candidates"]:
            candidate["price"] = format_catalog_price(
                cheapest.get(candidate["canonical_id"]),
                reference.get(candidate["canonical_id"]),
                lang=lang,
            )


async def cheapest_prices(
    session: AsyncSession, canonical_ids: Sequence[int]
) -> dict[int, Decimal]:
    """Cheapest live pack price per product.

    `get_active_offers_for_canonicals` orders by (canonical_id,
    price_per_base_unit), so the first offer seen for a product is its cheapest.
    """
    if not canonical_ids:
        return {}
    offers = await ShopRepository(session).get_active_offers_for_canonicals(list(canonical_ids))
    cheapest: dict[int, Decimal] = {}
    for offer in offers:
        if offer.canonical_id is not None and offer.canonical_id not in cheapest:
            cheapest[offer.canonical_id] = offer.price_per_pack
    return cheapest


async def _reference_prices(
    session: AsyncSession, canonical_ids: Sequence[int]
) -> dict[int, Decimal | None]:
    """The supplier list price per product, for rows no shop has priced yet."""
    if not canonical_ids:
        return {}
    stmt = select(CanonicalProduct.id, CanonicalProduct.reference_price).where(
        CanonicalProduct.id.in_(list(canonical_ids))
    )
    rows = (await session.execute(stmt)).all()
    return {int(row[0]): row[1] for row in rows}


async def validate_lines(session: AsyncSession, raw_lines: object) -> ValidatedBasket:
    """Turn the browser's basket into optimizer input, dropping anything invalid.

    A line survives only if it names a product that exists, is active, and sits
    inside the categories we actually carry -- the same allowlist the matcher
    honours, re-checked here because this input arrived from a client.
    """
    if not isinstance(raw_lines, list):
        return ValidatedBasket(items=(), rejected=())

    lines = [raw for raw in raw_lines[:_MAX_BASKET_LINES] if isinstance(raw, dict)]
    repo = CatalogRepository(session)
    enabled = await repo.enabled_category_ids()
    allowed = set(enabled) if enabled is not None else None

    # One lookup for the whole basket, not one per line: this runs on the path
    # to every quote, and SPEC §8.4 budgets the quote query, not a walk of it.
    wanted = {raw.get("canonical_id") for raw in lines if isinstance(raw.get("canonical_id"), int)}
    products: dict[int, CanonicalProduct] = {}
    if wanted:
        found = await session.execute(
            select(CanonicalProduct).where(CanonicalProduct.id.in_(list(wanted)))
        )
        products = {product.id: product for product in found.scalars().all()}

    items: list[BasketItemQuery] = []
    rejected: list[int] = []
    for index, raw in enumerate(lines, start=1):
        canonical_id = raw.get("canonical_id")
        qty = _decode_qty(raw.get("qty"))
        if not isinstance(canonical_id, int) or qty is None:
            rejected.append(index)
            continue

        product = products.get(canonical_id)
        if product is None or not product.is_active:
            rejected.append(index)
            continue
        if allowed is not None and product.category_id not in allowed:
            rejected.append(index)
            continue

        unit_code = raw.get("unit_code")
        items.append(
            BasketItemQuery(
                line_no=int(raw.get("line_no") or index),
                canonical_id=product.id,
                name_uz=product.name_uz,
                needed_qty=qty,
                unit_code=unit_code
                if isinstance(unit_code, str) and unit_code
                else product.base_unit_code,
            )
        )

    return ValidatedBasket(items=tuple(items), rejected=tuple(rejected))


async def optimize(
    session: AsyncSession,
    items: Sequence[BasketItemQuery],
    *,
    district_id: int | None,
) -> tuple[QuoteVariant, ...]:
    """Run the optimizer and return the variants worth showing."""
    if not items:
        return ()
    service = QuoteService(ShopRepository(session), CatalogRepository(session))
    result = await service.optimize_basket(list(items), district_id=district_id)
    return tuple(variant for variant in result.deduplicated_variants if variant.is_orderable)


def strategy_label(variant: QuoteVariant, lang: str) -> str:
    if not variant.strategy_labels:
        return t("web_quote_cheapest", lang=lang)
    return t(STRATEGY_LABEL_KEYS[variant.strategy_labels[0]], lang=lang)


def variant_payload(
    variant: QuoteVariant, lang: str, *, delivery_known: bool = True
) -> dict[str, Any]:
    """Render a variant for the browser.

    White-label on purpose, exactly as the bot's card is: the lines from every
    shop are merged into one list with no shop names, distances or per-shop
    subtotals. The customer buys from QurBot; the sourcing split is internal.

    `delivery_known` is False before we know where the order is going. Delivery
    is priced per district, so without one the optimiser finds no rule and the
    fee comes out zero -- shown plainly that would read as "free delivery" and
    then jump at checkout. Saying "after you choose an address" is the truth,
    and it is what stops the total from looking like a bait.
    """
    currency = t("web_currency", lang=lang)
    items = [
        {
            "name": line.product_name,
            "qty": f"{format_qty(line.billed_qty)} {line.pack_unit}",
            "cost": f"{format_uzs(line.line_cost_uzs)} {currency}",
        }
        for group in variant.shop_groups
        for line in group.lines
    ]
    return {
        "strategies": [label.value for label in variant.strategy_labels],
        "strategy": (
            variant.strategy_labels[0].value
            if variant.strategy_labels
            else OptimizationStrategy.CHEAPEST_TOTAL.value
        ),
        "title": strategy_label(variant, lang),
        "items": items,
        "items_total": f"{format_uzs(variant.items_total_uzs)} {currency}",
        "delivery_total": (
            f"{format_uzs(variant.delivery_total_uzs)} {currency}"
            if delivery_known
            else t("web_quote_delivery_unknown", lang=lang)
        ),
        "delivery_note": None if delivery_known else t("web_quote_delivery_note", lang=lang),
        "grand_total": f"{format_uzs(variant.grand_total_uzs)} {currency}",
        "grand_total_raw": str(variant.grand_total_uzs),
        "savings": (
            t(
                "quote_savings",
                lang=lang,
                amount=format_uzs(variant.savings_vs_worst_uzs),
                pct=f"{variant.savings_pct:.1f}",
            )
            if variant.savings_vs_worst_uzs > Decimal("0")
            else None
        ),
        "coverage": t(
            "quote_coverage",
            lang=lang,
            covered=variant.covered_count,
            total=variant.total_count,
        ),
        "eta": t(
            "quote_delivery_eta",
            lang=lang,
            eta_min=settings.delivery_eta_min_hours,
            eta_max=settings.delivery_eta_max_hours,
        ),
        "missing": [item.name_uz for item in variant.missing_lines],
    }


def pick_variant(variants: Sequence[QuoteVariant], strategy: str | None) -> QuoteVariant | None:
    """The variant the customer chose, by strategy label rather than position.

    Prices move between viewing a quote and confirming it, which can reorder or
    merge variants. Re-selecting by label keeps "the cheapest one" meaning the
    cheapest one, instead of whatever ended up at index 2.
    """
    if not variants:
        return None
    if strategy:
        for variant in variants:
            if any(label.value == strategy for label in variant.strategy_labels):
                return variant
    return variants[0]
