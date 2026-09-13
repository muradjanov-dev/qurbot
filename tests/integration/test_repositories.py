from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CanonicalProduct,
    Category,
    Unit,
)
from app.db.repositories import (
    BasketRepository,
    CatalogRepository,
    OpsRepository,
    UserRepository,
)


@pytest.mark.asyncio
async def test_catalog_repository(test_session: AsyncSession) -> None:
    repo = CatalogRepository(test_session)

    unit = Unit(code="dona", name_uz="Dona", name_ru="Штука", dimension="count")
    test_session.add(unit)

    cat = Category(slug="gisht", name_uz="G'isht", name_ru="Кирпич")
    test_session.add(cat)
    await test_session.flush()

    prod = CanonicalProduct(
        slug="gisht-m100",
        name_uz="G'isht M100",
        name_uz_cyrl="Ғишт М100",
        name_ru="Кирпич М100",
        category_id=cat.id,
        base_unit_code=unit.code,
        attributes={"grade": "M100"},
        search_doc="gisht m100",
    )
    test_session.add(prod)
    await test_session.flush()

    # Test get by slug
    fetched = await repo.get_canonical_by_slug("gisht-m100")
    assert fetched is not None
    assert fetched.name_uz == "G'isht M100"

    # Test search
    results = await repo.search_canonical_products("m100")
    assert len(results) >= 1
    assert results[0].slug == "gisht-m100"


@pytest.mark.asyncio
async def test_user_and_basket_repository(test_session: AsyncSession) -> None:
    user_repo = UserRepository(test_session)
    basket_repo = BasketRepository(test_session)

    # 1. Upsert user
    user = await user_repo.upsert_user(
        tg_id=999888777,
        username="test_buyer",
        full_name="Test Buyer",
        lang="uz_latn",
    )
    assert user.id is not None
    assert user.tg_id == 999888777

    # 2. Create Basket with Lines
    basket = await basket_repo.create_basket(user.id, "10 qop sement, 500 dona g'isht")
    assert basket.id is not None
    assert basket.status == "parsing"

    lines = await basket_repo.add_lines(
        basket_id=basket.id,
        lines_data=[
            {
                "line_no": 1,
                "raw_text": "10 qop sement",
                "parsed_name": "sement",
                "qty": Decimal("10"),
                "unit_code": None,
            },
            {
                "line_no": 2,
                "raw_text": "500 dona g'isht",
                "parsed_name": "g'isht",
                "qty": Decimal("500"),
                "unit_code": "dona",
            },
        ],
    )
    assert len(lines) == 2

    # 3. Create Quote
    quote = await basket_repo.create_quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("1200000.00"),
        delivery_total=Decimal("40000.00"),
        grand_total=Decimal("1240000.00"),
        coverage_pct=Decimal("100.00"),
        shop_count=1,
        payload={"strategy": "cheapest"},
    )
    assert quote.id is not None
    assert quote.grand_total == Decimal("1240000.00")


@pytest.mark.asyncio
async def test_ops_repository(test_session: AsyncSession) -> None:
    ops_repo = OpsRepository(test_session)

    # Record unmatched query
    q1 = await ops_repo.record_unmatched_query(
        "super yopishtiruvchi 50kg", "super yopishtiruvchi 50kg"
    )
    assert q1.occurrences == 1

    # Increment occurrence
    q2 = await ops_repo.record_unmatched_query(
        "super yopishtiruvchi 50kg", "super yopishtiruvchi 50kg"
    )
    assert q2.id == q1.id
    assert q2.occurrences == 2

    # Log event
    evt = await ops_repo.log_event("quote_generated", props={"strategy": "fastest"})
    assert evt.id is not None
    assert evt.name == "quote_generated"
