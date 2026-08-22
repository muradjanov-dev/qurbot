"""Deleting the system-seeded catalogue.

Migration 0010 deactivated the seeded shops; what it left behind was a
catalogue of products with no offers and no prices, which is what an operator
saw when they opened the admin catalogue screen. 0011 deletes them.

Deleting is not reversible, so these tests pin the two things that make it
safe: it takes only rows the seed created, and it never deletes a product some
real order was placed against -- `order_items.canonical_id` is NOT NULL, so
that would take the order history with it.
"""

import importlib.util
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct, Category, ProductAlias
from app.db.models.order import Basket, Order, OrderItem, OrderShopPart, Quote
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User
from scripts.seed import seed_database

_MIGRATION = pathlib.Path("migrations/versions/0011_purge_seeded_catalog.py")


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("purge_seeded_catalog", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seeded_products(session: AsyncSession) -> list[CanonicalProduct]:
    """Products as they looked before `source` existed: everything is 'seed'."""
    await seed_database(session, catalog_only=True)
    products = list((await session.execute(select(CanonicalProduct))).scalars().all())
    for product in products:
        product.source = "seed"
    await session.flush()
    return products


async def _purge(session: AsyncSession) -> tuple[int, int, int]:
    migration = _load_migration()
    connection = await session.connection()
    result: tuple[int, int, int] = await connection.run_sync(
        lambda sync_conn: migration.purge_seeded_catalog(sync_conn)
    )
    return result


@pytest.mark.asyncio
async def test_seeded_products_and_their_aliases_are_deleted(
    test_session: AsyncSession,
) -> None:
    await _seeded_products(test_session)

    deleted, aliases, kept = await _purge(test_session)

    assert deleted > 0
    assert aliases > 0
    assert kept == 0
    assert (
        await test_session.scalar(select(func.count(CanonicalProduct.id)))
    ) == 0, "no seeded product should survive"
    assert (await test_session.scalar(select(func.count(ProductAlias.id)))) == 0


@pytest.mark.asyncio
async def test_a_supplier_product_is_left_alone(test_session: AsyncSession) -> None:
    """Only rows the seed invented go; a transcribed price list stays."""
    products = await _seeded_products(test_session)
    keeper = products[0]
    keeper.source = "supplier"
    keeper.source_ref = "fanera.uz"
    await test_session.flush()

    deleted, _, _ = await _purge(test_session)

    assert deleted == len(products) - 1
    survivor = await test_session.get(CanonicalProduct, keeper.id)
    assert survivor is not None
    assert survivor.source == "supplier"


@pytest.mark.asyncio
async def test_a_product_with_an_order_against_it_survives(
    test_session: AsyncSession,
) -> None:
    """Order history outranks tidiness: order_items.canonical_id is NOT NULL."""
    products = await _seeded_products(test_session)
    ordered_product = products[0]

    district = (await test_session.execute(select(District).limit(1))).scalars().first()
    assert district is not None
    category = (await test_session.execute(select(Category).limit(1))).scalars().first()
    assert category is not None

    user = User(tg_id=987654, full_name="Xaridor", role="customer", lang="uz_latn")
    shop = Shop(
        name="Haqiqiy Do'kon",
        phone="+998901234567",
        district_id=district.id,
        address="Haqiqiy manzil 1",
        is_active=True,
    )
    test_session.add_all([user, shop])
    await test_session.flush()

    offer = ShopProduct(
        shop_id=shop.id,
        canonical_id=ordered_product.id,
        raw_name=ordered_product.name_uz,
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("157000"),
        price_per_base_unit=Decimal("157000"),
        is_active=True,
    )
    test_session.add(offer)
    await test_session.flush()

    basket = Basket(user_id=user.id, raw_text="fanera 12mm 1 dona", status="ordered")
    test_session.add(basket)
    await test_session.flush()

    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("157000"),
        delivery_total=Decimal("0"),
        grand_total=Decimal("157000"),
        coverage_pct=Decimal("100.00"),
        shop_count=1,
    )
    test_session.add(quote)
    await test_session.flush()

    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        status="new",
        contact_phone="+998901234567",
        delivery_address="Chilonzor tumani, Bunyodkor 12",
        grand_total_quoted=Decimal("157000"),
    )
    test_session.add(order)
    await test_session.flush()

    part = OrderShopPart(
        order_id=order.id,
        shop_id=shop.id,
        status="new",
        subtotal=Decimal("157000"),
        delivery_fee=Decimal("0"),
    )
    test_session.add(part)
    await test_session.flush()

    test_session.add(
        OrderItem(
            order_shop_part_id=part.id,
            canonical_id=ordered_product.id,
            shop_product_id=offer.id,
            qty=Decimal("1"),
            unit_code="dona",
            unit_price_quoted=Decimal("157000"),
            line_total=Decimal("157000"),
        )
    )
    await test_session.flush()

    _, _, kept = await _purge(test_session)

    assert kept == 1
    survivor = await test_session.get(CanonicalProduct, ordered_product.id)
    assert survivor is not None, "a product with an order against it must not be deleted"
    assert (await test_session.scalar(select(func.count(OrderItem.id)))) == 1


@pytest.mark.asyncio
async def test_nullable_references_are_released_not_orphaned(
    test_session: AsyncSession,
) -> None:
    """An offer pointing at a deleted product loses the link, not its row."""
    products = await _seeded_products(test_session)

    district = (await test_session.execute(select(District).limit(1))).scalars().first()
    assert district is not None
    shop = Shop(
        name="Boshqa Do'kon",
        phone="+998901112233",
        district_id=district.id,
        address="Manzil 2",
        is_active=True,
    )
    test_session.add(shop)
    await test_session.flush()

    offer = ShopProduct(
        shop_id=shop.id,
        canonical_id=products[0].id,
        raw_name="Fanera",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("120000"),
        price_per_base_unit=Decimal("120000"),
        is_active=True,
    )
    test_session.add(offer)
    await test_session.flush()

    await _purge(test_session)

    await test_session.refresh(offer)
    assert offer.canonical_id is None
    assert offer.price_per_pack == Decimal("120000")
