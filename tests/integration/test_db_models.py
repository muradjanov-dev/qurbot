from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CanonicalProduct,
    Category,
    District,
    ProductAlias,
    Shop,
    ShopDeliveryRule,
    Unit,
)


@pytest.mark.asyncio
async def test_create_and_query_catalog_models(test_session: AsyncSession) -> None:
    # 1. Unit
    unit = Unit(
        code="kg",
        name_uz="Kilogramm",
        name_ru="Килограмм",
        dimension="mass",
        factor_to_base=Decimal("1.0000"),
    )
    test_session.add(unit)
    await test_session.flush()

    # 2. Category
    category = Category(
        slug="sement",
        name_uz="Sement",
        name_ru="Цемент",
        sort_order=1,
    )
    test_session.add(category)
    await test_session.flush()

    # 3. Canonical Product
    product = CanonicalProduct(
        slug="sement-m400-50kg",
        name_uz="Sement M400 50kg",
        name_uz_cyrl="Цемент М400 50кг",
        name_ru="Цемент М400 50кг",
        brand="Qizilqum",
        category_id=category.id,
        base_unit_code=unit.code,
        attributes={"grade": "M400", "weight_kg": 50},
        tier="standard",
        is_active=True,
        search_doc="sement m400 qizilqum 50kg",
    )
    test_session.add(product)
    await test_session.flush()

    # 4. Product Alias
    alias = ProductAlias(
        canonical_id=product.id,
        alias_norm="sement m400",
        alias_raw="Sement M400",
        source="seed",
        confidence=Decimal("1.00"),
        is_approved=True,
    )
    test_session.add(alias)
    await test_session.flush()

    # Verify query
    stmt = select(CanonicalProduct).where(CanonicalProduct.slug == "sement-m400-50kg")
    result = await test_session.execute(stmt)
    fetched = result.scalars().first()

    assert fetched is not None
    assert fetched.name_uz == "Sement M400 50kg"
    assert fetched.base_unit_code == "kg"
    assert len(fetched.aliases) == 1
    assert fetched.aliases[0].alias_norm == "sement m400"


@pytest.mark.asyncio
async def test_create_and_query_shop_models(test_session: AsyncSession) -> None:
    # 1. District
    district = District(
        region="Toshkent",
        name_uz="Chilonzor tumani",
        name_ru="Чиланзарский район",
        centroid_lat=Decimal("41.2721"),
        centroid_lng=Decimal("69.2045"),
    )
    test_session.add(district)
    await test_session.flush()

    # 2. Shop
    shop = Shop(
        name="Baraka Qurilish",
        phone="+998901234567",
        district_id=district.id,
        address="Chilonzor 19",
        is_active=True,
        rating=Decimal("4.9"),
        trust_score=Decimal("0.98"),
        working_hours={"mon_fri": "08:00-19:00"},
        payment_methods=["cash", "card"],
    )
    test_session.add(shop)
    await test_session.flush()

    # 3. Delivery Rule
    rule = ShopDeliveryRule(
        shop_id=shop.id,
        district_id=district.id,
        fee=Decimal("30000.00"),
        free_above=Decimal("1000000.00"),
        min_order=Decimal("50000.00"),
        eta_hours=12,
    )
    test_session.add(rule)
    await test_session.flush()

    # Verify
    stmt = select(Shop).where(Shop.id == shop.id)
    res = await test_session.execute(stmt)
    fetched_shop = res.scalars().first()

    assert fetched_shop is not None
    assert fetched_shop.name == "Baraka Qurilish"
    assert len(fetched_shop.delivery_rules) == 1
    assert fetched_shop.delivery_rules[0].fee == Decimal("30000.00")
