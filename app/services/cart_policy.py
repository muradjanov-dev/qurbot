"""Live sellability for every cart doorway. No guessed price or stock."""

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainException
from app.db.models.catalog import CanonicalProduct
from app.db.repositories.shop_repo import ShopRepository
from app.domain.models import OfferPricing
from app.domain.pricing.units import line_cost


def _line_price(line: dict[str, Any], offers: Sequence[Any]) -> dict[str, str | None]:
    """Show a cart-line estimate using the same pack and tier rules as quoting."""
    qty = Decimal(str(line["qty"]))
    choices: list[tuple[Decimal, int, Decimal, Any]] = []
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
                tier.price_per_pack
                for tier in offer.price_tiers
                if Decimal(initial.packs_needed) >= tier.min_qty
            ]
            unit_price = min([offer.price_per_pack, *eligible])
            cost = line_cost(
                qty, str(line["unit_code"]), replace(pricing, price_per_pack=unit_price)
            ).cost
        except DomainException:
            continue
        choices.append((cost, offer.id, unit_price, offer))
    if not choices:
        return {
            "line_total_uzs": None,
            "display_unit_price_uzs": None,
            "display_pack_price_uzs": None,
            "display_pack_size": None,
            "display_pack_unit": None,
        }
    cost, _, unit_price, offer = min(choices, key=lambda item: (item[0], item[1]))
    return {
        "line_total_uzs": str(cost),
        "display_unit_price_uzs": str(unit_price)
        if offer.pack_size == 1 and (offer.pack_unit_code or offer.raw_unit) == line["unit_code"]
        else None,
        "display_pack_price_uzs": str(unit_price),
        "display_pack_size": format(offer.pack_size.normalize(), "f"),
        "display_pack_unit": offer.pack_unit_code or offer.raw_unit,
    }


async def assess_lines(
    session: AsyncSession, lines: Sequence[dict[str, Any]]
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
        display = (
            _line_price(line, candidates)
            if not unknown
            else {
                "line_total_uzs": None,
                "display_unit_price_uzs": None,
                "display_pack_price_uzs": None,
                "display_pack_size": None,
                "display_pack_unit": None,
            }
        )
        result.append(
            {
                **line,
                "requires_confirmation": bool(unknown),
                "reference_unit_price": str(price) if price is not None else None,
                "price_unit_code": product.base_unit_code if product else line["unit_code"],
                **display,
            }
        )
    return result
