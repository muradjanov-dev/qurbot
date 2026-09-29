"""Live sellability for every cart doorway. No guessed price or stock."""

from collections.abc import Sequence
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainException
from app.db.models.catalog import CanonicalProduct
from app.db.repositories.shop_repo import ShopRepository
from app.domain.models import OfferPricing
from app.domain.pricing.display import usd_equivalent
from app.domain.pricing.units import line_cost


def _empty_price_view() -> dict[str, str | None | bool | int]:
    return {
        "line_total_uzs": None,
        "line_total_usd": None,
        "line_total_usd_approximate": False,
        "display_unit_price_uzs": None,
        "display_unit_price_usd": None,
        "display_unit_price_usd_approximate": False,
        "display_pack_price_uzs": None,
        "display_pack_price_usd": None,
        "display_pack_price_usd_approximate": False,
        "display_pack_size": None,
        "display_pack_unit": None,
    }


def _line_price(
    line: dict[str, Any], offers: Sequence[Any], *, rate: Decimal | None
) -> dict[str, str | None | bool | int]:
    """Show a cart-line estimate using the same pack and tier rules as quoting."""
    qty = Decimal(str(line["qty"]))
    choices: list[tuple[Decimal, int, Decimal, Any, Any | None, Decimal]] = []
    for offer in offers:
        if offer.pack_size <= 0:
            continue
        pack_unit = offer.pack_unit_code or offer.raw_unit
        pricing = OfferPricing(
            shop_product_id=offer.id,
            shop_id=offer.shop_id,
            canonical_id=offer.canonical_id,
            raw_name=offer.raw_name,
            pack_size=offer.pack_size,
            pack_unit=pack_unit,
            price_per_pack=offer.price_per_pack,
            price_per_base_unit=offer.price_per_base_unit,
        )
        try:
            initial = line_cost(qty, str(line["unit_code"]), pricing)
            eligible = [
                tier for tier in offer.price_tiers if Decimal(initial.packs_needed) >= tier.min_qty
            ]
            selected_tier = min(
                eligible, key=lambda tier: (tier.price_per_pack, tier.id), default=None
            )
            if selected_tier is not None and selected_tier.price_per_pack < offer.price_per_pack:
                unit_price = selected_tier.price_per_pack
            else:
                selected_tier = None
                unit_price = offer.price_per_pack
            line_cost_result = line_cost(
                qty, str(line["unit_code"]), replace(pricing, price_per_pack=unit_price)
            )
        except DomainException:
            continue
        choices.append(
            (
                line_cost_result.cost,
                offer.id,
                unit_price,
                offer,
                selected_tier,
                Decimal(line_cost_result.packs_needed),
            )
        )
    if not choices:
        return _empty_price_view()
    line_total, _, unit_price, offer, tier, packs_needed = min(
        choices, key=lambda item: (item[0], item[1])
    )
    source_currency = tier.source_currency if tier is not None else offer.source_currency
    source_price = tier.source_price_per_pack if tier is not None else offer.source_price_per_pack
    original_usd = source_currency == "USD" and source_price is not None
    pack_price_usd = (
        source_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if original_usd
        else usd_equivalent(unit_price, rate)
    )
    if original_usd:
        line_total_usd = (source_price * packs_needed).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        approximate = False
    else:
        line_total_usd = usd_equivalent(line_total, rate)
        approximate = line_total_usd is not None
    display_unit_price = (
        str(unit_price)
        if offer.pack_size == 1 and (offer.pack_unit_code or offer.raw_unit) == line["unit_code"]
        else None
    )
    return {
        "line_total_uzs": str(line_total),
        "line_total_usd": str(line_total_usd) if line_total_usd is not None else None,
        "line_total_usd_approximate": approximate,
        "display_unit_price_uzs": display_unit_price,
        "display_unit_price_usd": str(pack_price_usd)
        if display_unit_price and pack_price_usd is not None
        else None,
        "display_unit_price_usd_approximate": bool(
            display_unit_price and pack_price_usd is not None and not original_usd
        ),
        "display_pack_price_uzs": str(unit_price),
        "display_pack_price_usd": str(pack_price_usd) if pack_price_usd is not None else None,
        "display_pack_price_usd_approximate": bool(pack_price_usd is not None and not original_usd),
        "display_pack_size": format(offer.pack_size.normalize(), "f"),
        "display_pack_unit": offer.pack_unit_code or offer.raw_unit,
    }


async def assess_lines(
    session: AsyncSession,
    lines: Sequence[dict[str, Any]],
    *,
    rate: Decimal | None = None,
    fx_revision: int | None = None,
) -> list[dict[str, Any]]:
    ids = [int(line["canonical_id"]) for line in lines]
    products = {
        p.id: p
        for p in (
            await session.scalars(select(CanonicalProduct).where(CanonicalProduct.id.in_(ids)))
        ).all()
    }
    offers = await ShopRepository(session).get_active_offers_for_canonicals(ids)
    result = []
    for line in lines:
        product = products.get(line["canonical_id"])
        candidates = [
            o
            for o in offers
            if o.canonical_id == line["canonical_id"]
            and o.shop
            and o.shop.is_active
            and o.price_per_base_unit > 0
            and o.stock_status in {"in_stock", "low"}
        ]
        unknown = (
            not product
            or not product.is_active
            or not candidates
            or bool(
                product.attributes.get("price_on_request")
                or product.attributes.get("stock_unverified")
            )
        )
        price = (
            min((o.price_per_base_unit for o in candidates), default=None) if not unknown else None
        )
        display = _line_price(line, candidates, rate=rate) if not unknown else _empty_price_view()
        result.append(
            {
                **line,
                "requires_confirmation": bool(unknown),
                "reference_unit_price": str(price) if price is not None else None,
                "price_unit_code": product.base_unit_code if product else line["unit_code"],
                "fx_revision": fx_revision,
                **display,
            }
        )
    return result
