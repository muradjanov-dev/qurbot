"""Live sellability for every cart doorway. No guessed price or stock."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct
from app.db.repositories.shop_repo import ShopRepository


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
        result.append(
            {
                **line,
                "requires_confirmation": bool(unknown),
                "reference_unit_price": str(price) if price is not None else None,
                "price_unit_code": product.base_unit_code if product else line["unit_code"],
            }
        )
    return result
