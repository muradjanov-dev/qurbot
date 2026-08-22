from decimal import Decimal

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
from scripts.seed import FANERA_UZ, SOURCE_SUPPLIER, generate_catalog_data, seed_database


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

    # Verify Canonical Products. The catalogue is exactly what the supplier
    # price lists carry, so a count that drifts from the source data is a
    # regression rather than growth.
    prod_count = (await test_session.execute(select(func.count(CanonicalProduct.id)))).scalar()
    assert prod_count == len(generate_catalog_data())

    # Verify Product Aliases
    alias_count = (await test_session.execute(select(func.count(ProductAlias.id)))).scalar()
    assert alias_count is not None and alias_count >= prod_count

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


@pytest.mark.asyncio
async def test_catalog_records_where_each_product_came_from(
    test_session: AsyncSession,
) -> None:
    """Provenance is what separates a real row from a placeholder.

    The admin catalogue screen showed 222 rows with no price and no way to
    tell which were invented by the seed, which is why `source` exists.
    """
    await seed_database(test_session, catalog_only=True)

    products = (await test_session.execute(select(CanonicalProduct))).scalars().all()
    assert products
    assert {p.source for p in products} == {SOURCE_SUPPLIER}
    assert {p.source_ref for p in products} == {FANERA_UZ}


@pytest.mark.asyncio
async def test_negotiable_prices_are_null_not_zero(test_session: AsyncSession) -> None:
    """ "Kelishiladi" means the price is agreed per order, not that it is free.

    A zero would win every comparison the optimiser makes.
    """
    await seed_database(test_session, catalog_only=True)

    negotiable = {item.slug for item in generate_catalog_data() if item.reference_price is None}
    assert negotiable, "the price list has negotiable rows; the fixture should cover them"

    rows = (await test_session.execute(select(CanonicalProduct))).scalars().all()
    for product in rows:
        if product.slug in negotiable:
            assert product.reference_price is None
        else:
            assert product.reference_price is not None
            assert product.reference_price > 0


@pytest.mark.asyncio
async def test_reseeding_republishes_changed_prices(test_session: AsyncSession) -> None:
    """A price list is republished, not re-created.

    fanera.uz says prices move with the order day, so a re-seed has to reach
    rows that already exist or the catalogue keeps whatever the first run
    happened to load.
    """
    await seed_database(test_session, catalog_only=True)

    slug = next(i.slug for i in generate_catalog_data() if i.reference_price is not None)
    product = (
        (await test_session.execute(select(CanonicalProduct).where(CanonicalProduct.slug == slug)))
        .scalars()
        .first()
    )
    assert product is not None
    original = product.reference_price

    product.reference_price = Decimal("1")
    await test_session.commit()

    await seed_database(test_session, catalog_only=True)
    await test_session.refresh(product)
    assert product.reference_price == original


@pytest.mark.asyncio
async def test_a_product_dropped_from_the_price_list_is_retired(
    test_session: AsyncSession,
) -> None:
    """Seeding is insert-or-update, so removals need their own step.

    Without it a row taken off the price list stays in the live catalogue for
    good -- which is what happened to the DSP rows after they were held back.
    """
    await seed_database(test_session, catalog_only=True)

    stale = CanonicalProduct(
        slug="dsp-kronospan-1-6mm-2750x1830",
        name_uz="DSP plita Kronospan 1.6 mm (2750x1830)",
        name_uz_cyrl="ДСП плита Kronospan 1.6 мм (2750х1830)",
        name_ru="ДСП плита Kronospan 1.6 мм (2750х1830)",
        brand="Kronospan",
        category_id=(
            await test_session.scalar(select(Category.id).where(Category.slug == "plita-va-fanera"))
        ),
        base_unit_code="dona",
        attributes={},
        tier="standard",
        source=SOURCE_SUPPLIER,
        source_ref=FANERA_UZ,
        reference_price=Decimal("260000"),
        is_active=True,
        search_doc="dsp plita kronospan",
    )
    test_session.add(stale)
    await test_session.flush()

    await seed_database(test_session, catalog_only=True)
    await test_session.refresh(stale)

    assert stale.is_active is False, "a product no longer on the price list must be retired"

    # Everything still on the list stays live.
    live = await test_session.scalar(
        select(func.count(CanonicalProduct.id)).where(CanonicalProduct.is_active.is_(True))
    )
    assert live == len(generate_catalog_data())


@pytest.mark.asyncio
async def test_retiring_leaves_rows_from_other_sources_alone(
    test_session: AsyncSession,
) -> None:
    """A product an admin added is not ours to retire off a supplier's list."""
    await seed_database(test_session, catalog_only=True)

    admin_product = CanonicalProduct(
        slug="admin-qoshgan-mahsulot",
        name_uz="Admin qo'shgan mahsulot",
        name_uz_cyrl="Админ қўшган маҳсулот",
        name_ru="Товар добавлен админом",
        brand=None,
        category_id=(
            await test_session.scalar(select(Category.id).where(Category.slug == "plita-va-fanera"))
        ),
        base_unit_code="dona",
        attributes={},
        tier="standard",
        source="admin",
        source_ref=None,
        reference_price=Decimal("99000"),
        is_active=True,
        search_doc="admin qoshgan mahsulot",
    )
    test_session.add(admin_product)
    await test_session.flush()

    await seed_database(test_session, catalog_only=True)
    await test_session.refresh(admin_product)

    assert admin_product.is_active is True
