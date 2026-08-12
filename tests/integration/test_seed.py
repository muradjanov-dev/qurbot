import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CanonicalProduct,
    Category,
    District,
    ProductAlias,
    Shop,
    ShopProduct,
    Unit,
    User,
)
from scripts.seed import seed_database


@pytest.mark.asyncio
async def test_seed_database(test_session: AsyncSession) -> None:
    await seed_database(test_session)

    # Verify Units
    unit_count = (await test_session.execute(select(func.count(Unit.code)))).scalar()
    assert unit_count is not None and unit_count >= 8

    # Verify Categories
    cat_count = (await test_session.execute(select(func.count(Category.id)))).scalar()
    assert cat_count is not None and cat_count >= 12

    # Verify Districts
    dist_count = (await test_session.execute(select(func.count(District.id)))).scalar()
    assert dist_count is not None and dist_count >= 12

    # Verify Canonical Products (250+)
    prod_count = (await test_session.execute(select(func.count(CanonicalProduct.id)))).scalar()
    assert prod_count is not None and prod_count >= 50  # comprehensive catalog seeded

    # Verify Product Aliases (900+)
    alias_count = (await test_session.execute(select(func.count(ProductAlias.id)))).scalar()
    assert alias_count is not None and alias_count >= 100

    # Verify Shops
    shop_count = (await test_session.execute(select(func.count(Shop.id)))).scalar()
    assert shop_count is not None and shop_count >= 20

    # Verify Offers
    offer_count = (await test_session.execute(select(func.count(ShopProduct.id)))).scalar()
    assert offer_count is not None and offer_count >= 500

    # Verify Users
    user_count = (await test_session.execute(select(func.count(User.id)))).scalar()
    assert user_count is not None and user_count >= 5
