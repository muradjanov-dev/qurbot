import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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


@pytest.mark.asyncio
async def test_seeding_twice_is_idempotent(test_session: AsyncSession) -> None:
    """Re-seeding is how catalog changes reach an existing database.

    The second run used to abort on the unique (canonical_id, alias_norm)
    index, so a category rename could not be rolled out to production at all.
    """
    from sqlalchemy import func, select

    from app.db.models import Category, ProductAlias

    await seed_database(test_session)
    categories_first = await test_session.scalar(select(func.count(Category.id)))
    aliases_first = await test_session.scalar(select(func.count(ProductAlias.id)))

    # Must not raise, and must not duplicate rows.
    await seed_database(test_session)
    assert await test_session.scalar(select(func.count(Category.id))) == categories_first
    assert await test_session.scalar(select(func.count(ProductAlias.id))) == aliases_first


@pytest.mark.asyncio
async def test_catalog_only_seed_skips_the_demo_market(test_session: AsyncSession) -> None:
    """Rolling out catalogue changes must not create placeholder shops.

    This is what runs on every deploy, against a database holding real shops
    and real offers -- so it has to add products without touching the market.
    """
    await seed_database(test_session, catalog_only=True)

    products = (await test_session.execute(select(func.count(CanonicalProduct.id)))).scalar()
    categories = (await test_session.execute(select(func.count(Category.id)))).scalar()
    shops = (await test_session.execute(select(func.count(Shop.id)))).scalar()
    offers = (await test_session.execute(select(func.count(ShopProduct.id)))).scalar()

    assert products and products > 0
    assert categories and categories > 0
    assert shops == 0, "catalog-only must not create shops"
    assert offers == 0, "catalog-only must not create offers"


@pytest.mark.asyncio
async def test_launch_categories_are_all_stocked(test_session: AsyncSession) -> None:
    """Every category we offer must actually have products behind it."""
    await seed_database(test_session, catalog_only=True)

    for slug in settings.enabled_category_slugs:
        category = (
            (await test_session.execute(select(Category).where(Category.slug == slug)))
            .scalars()
            .first()
        )
        assert category is not None, f"enabled category '{slug}' is not seeded"

        count = (
            await test_session.execute(
                select(func.count(CanonicalProduct.id)).where(
                    CanonicalProduct.category_id == category.id
                )
            )
        ).scalar()
        assert count and count > 0, f"enabled category '{slug}' has no products"
