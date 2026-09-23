"""Apply the owner-approved plywood retail and wholesale price sheet.

Dry-run is the default. ``--apply`` updates only the active house-shop offer
for each exact canonical slug. Product identity, stock and supplier reference
prices are left unchanged. Retail changes append normal price-history rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct
from app.db.models.shop import Shop, ShopProduct, ShopProductPriceTier
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import async_session_factory
from scripts.seed import _OUR_PLYWOOD_PRICES, OUR_SHOP_NAME, USD_TO_UZS, _slug_num, _uzs

PRICE_LOCK = int.from_bytes(b"qbplywod", "big")


def approved_rows() -> list[tuple[str, Decimal, Decimal, Decimal]]:
    rows = [
        (
            f"fanera-bereza-{grade}-{_slug_num(thickness)}mm-{size}",
            _uzs(retail_usd),
            _uzs(wholesale_usd),
            Decimal(from_qty),
        )
        for size, grade, thickness, retail_usd, wholesale_usd, from_qty in _OUR_PLYWOOD_PRICES
    ]
    if len(rows) != 20 or len({row[0] for row in rows}) != 20:
        raise RuntimeError("approved plywood source must contain 20 unique variants")
    return rows


async def update_prices(session: AsyncSession, *, apply: bool) -> dict[str, Any]:
    dialect = session.get_bind().dialect.name
    async with session.begin():
        if dialect == "postgresql":
            if apply:
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": PRICE_LOCK}
                )
            else:
                await session.execute(text("SET TRANSACTION READ ONLY"))

        shops = list(
            (
                await session.scalars(
                    select(Shop).where(Shop.name == OUR_SHOP_NAME, Shop.is_active.is_(True))
                )
            ).all()
        )
        if len(shops) != 1:
            raise RuntimeError(f"expected one active house shop, found {len(shops)}")
        shop = shops[0]
        changes: list[dict[str, Any]] = []
        repo = ShopRepository(session)

        for slug, retail, wholesale, minimum in approved_rows():
            product = await session.scalar(
                select(CanonicalProduct).where(
                    CanonicalProduct.slug == slug, CanonicalProduct.is_active.is_(True)
                )
            )
            if product is None:
                raise RuntimeError(f"active canonical product missing: {slug}")
            statement = select(ShopProduct).where(
                ShopProduct.shop_id == shop.id,
                ShopProduct.canonical_id == product.id,
                ShopProduct.is_active.is_(True),
            )
            if apply:
                statement = statement.with_for_update()
            offers = list((await session.scalars(statement)).all())
            if len(offers) != 1:
                raise RuntimeError(
                    f"expected one active house offer for {slug}, found {len(offers)}"
                )
            offer = offers[0]
            if (
                offer.pack_size != Decimal("1")
                or offer.pack_unit_code != "dona"
                or product.base_unit_code != "dona"
            ):
                raise RuntimeError(f"unexpected price basis for {slug}")

            tiers = list(
                (
                    await session.scalars(
                        select(ShopProductPriceTier).where(
                            ShopProductPriceTier.shop_product_id == offer.id
                        )
                    )
                ).all()
            )
            before_tiers = [
                {"min_qty": str(tier.min_qty), "price_per_pack": str(tier.price_per_pack)}
                for tier in tiers
            ]
            changes.append(
                {
                    "slug": slug,
                    "offer_id": offer.id,
                    "retail_before": str(offer.price_per_pack),
                    "retail_after": str(retail),
                    "retail_changed": offer.price_per_pack != retail,
                    "tiers_before": before_tiers,
                    "wholesale_after": str(wholesale),
                    "wholesale_from": str(minimum),
                }
            )
            if not apply:
                continue
            if offer.price_per_pack != retail:
                await repo.update_offer_price(offer.id, retail, retail, updated_by="admin")
            await session.execute(
                delete(ShopProductPriceTier).where(
                    ShopProductPriceTier.shop_product_id == offer.id,
                    ShopProductPriceTier.min_qty != minimum,
                )
            )
            tier = next((row for row in tiers if row.min_qty == minimum), None)
            if tier is None:
                session.add(
                    ShopProductPriceTier(
                        shop_product_id=offer.id,
                        min_qty=minimum,
                        price_per_pack=wholesale,
                    )
                )
            else:
                tier.price_per_pack = wholesale
        await session.flush()

    return {
        "mode": "apply" if apply else "dry-run",
        "usd_to_uzs": str(USD_TO_UZS),
        "shop_id": shop.id,
        "count": len(changes),
        "retail_changes": sum(bool(row["retail_changed"]) for row in changes),
        "rows": changes,
    }


async def run(apply: bool) -> dict[str, Any]:
    async with async_session_factory() as session:
        return await update_prices(session, apply=apply)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the approved prices")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.apply)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
