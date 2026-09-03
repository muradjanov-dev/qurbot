"""Retiring the seeded demo market.

The seeded shops carry synthetic prices (`50000 * random(0.92..1.15)`
regardless of product), so leaving them active means quoting customers numbers
that mean nothing. These tests pin the two properties that make the cleanup
safe: it hits exactly the seeded shops, and it is reversible.
"""

import importlib.util
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shop import District, Shop, ShopProduct
from scripts.seed import seed_database

_MIGRATION = pathlib.Path("migrations/versions/0010_retire_seeded_market.py")


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("retire_seeded_market", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _real_shop(session: AsyncSession) -> Shop:
    """A shop onboarded for real, which must survive the cleanup untouched."""
    district = (await session.execute(select(District).limit(1))).scalars().first()
    assert district is not None
    shop = Shop(
        name="Haqiqiy Do'kon",
        phone="+998901234567",
        owner_tg_id=777001,
        district_id=district.id,
        address="Haqiqiy manzil 1",
        is_active=True,
    )
    session.add(shop)
    await session.flush()
    session.add(
        ShopProduct(
            shop_id=shop.id,
            canonical_id=None,
            raw_name="Haqiqiy mahsulot",
            raw_unit="dona",
            pack_size=Decimal("1"),
            pack_unit_code="dona",
            price_per_pack=Decimal("99000"),
            price_per_base_unit=Decimal("99000"),
            is_active=True,
        )
    )
    await session.flush()
    return shop


@pytest.mark.asyncio
async def test_seeded_offers_are_deactivated_and_real_ones_are_not(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session)
    real = await _real_shop(test_session)
    migration = _load_migration()

    connection = await test_session.connection()
    offer_count, shop_count = await connection.run_sync(
        lambda sync_conn: migration.set_seeded_market_active(sync_conn, False)
    )

    assert shop_count == len(migration.SEEDED_SHOP_NAMES)
    assert offer_count > 0

    # Counting every active offer would now also count our own priced ones,
    # which the migration has no business touching. What it promises is
    # narrower: nothing belonging to a seeded shop stays active.
    seeded_still_active = (
        await test_session.execute(
            select(func.count(ShopProduct.id))
            .join(Shop, Shop.id == ShopProduct.shop_id)
            .where(
                ShopProduct.is_active.is_(True),
                Shop.name.in_(migration.SEEDED_SHOP_NAMES),
            )
        )
    ).scalar()
    assert seeded_still_active == 0, "no seeded shop's offer may stay active"

    real_offer = (
        (await test_session.execute(select(ShopProduct).where(ShopProduct.shop_id == real.id)))
        .scalars()
        .first()
    )
    assert real_offer is not None and real_offer.is_active is True

    refreshed_real = await test_session.get(Shop, real.id)
    assert refreshed_real is not None and refreshed_real.is_active is True


@pytest.mark.asyncio
async def test_the_cleanup_is_reversible(test_session: AsyncSession) -> None:
    """Downgrade must put the demo market back, exactly as promised."""
    await seed_database(test_session)
    migration = _load_migration()
    connection = await test_session.connection()

    before = (
        await test_session.execute(
            select(func.count(ShopProduct.id)).where(ShopProduct.is_active.is_(True))
        )
    ).scalar()

    await connection.run_sync(lambda c: migration.set_seeded_market_active(c, False))
    after_off = (
        await test_session.execute(
            select(func.count(ShopProduct.id))
            .join(Shop, Shop.id == ShopProduct.shop_id)
            .where(
                ShopProduct.is_active.is_(True),
                Shop.name.in_(migration.SEEDED_SHOP_NAMES),
            )
        )
    ).scalar()
    assert after_off == 0

    await connection.run_sync(lambda c: migration.set_seeded_market_active(c, True))
    after_on = (
        await test_session.execute(
            select(func.count(ShopProduct.id)).where(ShopProduct.is_active.is_(True))
        )
    ).scalar()
    assert after_on == before


@pytest.mark.asyncio
async def test_deactivated_offers_stop_reaching_quotes(test_session: AsyncSession) -> None:
    """The point of the exercise: synthetic prices must leave the quote path."""
    from app.db.repositories.shop_repo import ShopRepository

    await seed_database(test_session)
    canonical_ids = [
        row[0]
        for row in (await test_session.execute(select(ShopProduct.canonical_id).limit(20))).all()
        if row[0] is not None
    ]
    repo = ShopRepository(test_session)
    assert await repo.get_active_offers_for_canonicals(canonical_ids), "precondition"

    migration = _load_migration()
    connection = await test_session.connection()
    await connection.run_sync(lambda c: migration.set_seeded_market_active(c, False))

    assert await repo.get_active_offers_for_canonicals(canonical_ids) == []
