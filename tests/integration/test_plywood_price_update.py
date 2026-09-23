"""Approved plywood prices update existing offers without duplicate history."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct
from app.db.models.shop import PriceHistory, ShopProduct, ShopProductPriceTier
from scripts.seed import seed_database
from scripts.update_plywood_prices import approved_rows, update_prices


async def test_plywood_price_update_is_dry_run_safe_and_idempotent(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session, catalog_only=True)
    await test_session.commit()

    slug, retail, wholesale, minimum = approved_rows()[0]
    product = await test_session.scalar(
        select(CanonicalProduct).where(CanonicalProduct.slug == slug)
    )
    offer = await test_session.scalar(
        select(ShopProduct).where(ShopProduct.canonical_id == product.id)
    )
    tier = await test_session.scalar(
        select(ShopProductPriceTier).where(ShopProductPriceTier.shop_product_id == offer.id)
    )
    offer.price_per_pack = offer.price_per_base_unit = Decimal("1")
    tier.price_per_pack = Decimal("1")
    await test_session.commit()
    history_before = await test_session.scalar(
        select(func.count())
        .select_from(PriceHistory)
        .where(PriceHistory.shop_product_id == offer.id)
    )
    await test_session.commit()

    preview = await update_prices(test_session, apply=False)
    assert preview["count"] == 20 and preview["retail_changes"] == 1
    await test_session.refresh(offer)
    assert offer.price_per_pack == Decimal("1")
    await test_session.commit()

    applied = await update_prices(test_session, apply=True)
    assert applied["count"] == 20 and applied["retail_changes"] == 1
    await test_session.refresh(offer)
    await test_session.refresh(tier)
    assert offer.price_per_pack == retail
    assert tier.min_qty == minimum and tier.price_per_pack == wholesale
    history_after = await test_session.scalar(
        select(func.count())
        .select_from(PriceHistory)
        .where(PriceHistory.shop_product_id == offer.id)
    )
    assert history_after == history_before + 1
    await test_session.commit()

    repeated = await update_prices(test_session, apply=True)
    assert repeated["retail_changes"] == 0
    assert (
        await test_session.scalar(
            select(func.count())
            .select_from(PriceHistory)
            .where(PriceHistory.shop_product_id == offer.id)
        )
        == history_after
    )
