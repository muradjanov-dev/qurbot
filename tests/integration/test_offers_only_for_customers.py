"""A customer may only be offered what a shop actually sells.

The catalogue carries a supplier's entire price list; a shop stocks part of it.
Matching ignored that, so a customer asking for fanera was handed the catalogue
sheet nobody had, picked it, and got a quote of "0 so'm, Qamrov: 0/2 mahsulot"
-- which reads as a broken bot rather than an absent product, and leaves
nothing to press.

The shop side must keep the opposite behaviour: a shop uploading a price is
creating the first offer for that product, so requiring one would match
nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category
from app.db.models.shop import District, Shop, ShopProduct
from app.db.repositories.catalog_repo import CatalogRepository


@pytest.fixture(autouse=True)
def _full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enabled_category_slugs", [])


async def _catalogue_with_one_stocked_sheet(session: AsyncSession) -> tuple[int, int]:
    """Two near-identical products; only the first has an offer behind it."""
    category = Category(slug="plita-va-fanera", name_uz="Plita va fanera", name_ru="Плита")
    session.add(category)
    await session.flush()

    stocked = CanonicalProduct(
        slug="fanera-10mm-1525x1525",
        name_uz="Fanera 10 mm 1525x1525",
        name_uz_cyrl="Фанера 10 мм 1525х1525",
        name_ru="Фанера 10 мм 1525х1525",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="fanera 10 mm 1525x1525 фанера 10 мм",
        attributes={"thickness_mm": 10, "size": "1525x1525"},
    )
    unstocked = CanonicalProduct(
        slug="fanera-bereza-2x4-3mm-1525x1525",
        name_uz="Fanera berezovaya 2x4 3 mm (1525x1525)",
        name_uz_cyrl="Фанера березовая 2х4 3 мм",
        name_ru="Фанера березовая 2х4 3 мм",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="fanera berezovaya 2x4 3 mm 1525x1525 фанера березовая",
        attributes={"thickness_mm": 3, "size": "1525x1525", "grade": "2x4"},
    )
    session.add_all([stocked, unstocked])
    await session.flush()

    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()
    shop = Shop(
        name="Ark buloq",
        phone="+998901112233",
        district_id=district.id,
        address="Chilonzor 9-kvartal",
        is_active=True,
    )
    session.add(shop)
    await session.flush()

    session.add(
        ShopProduct(
            shop_id=shop.id,
            canonical_id=stocked.id,
            raw_name="Fanera 10 mm 1525x1525",
            raw_unit="dona",
            pack_size=Decimal("1"),
            pack_unit_code="dona",
            price_per_pack=Decimal("151000"),
            price_per_base_unit=Decimal("151000"),
            stock_status="in_stock",
            staleness_state="fresh",
            is_active=True,
        )
    )
    await session.flush()
    return stocked.id, unstocked.id


@pytest.mark.asyncio
async def test_customer_search_skips_products_nobody_sells(test_session: AsyncSession) -> None:
    stocked_id, unstocked_id = await _catalogue_with_one_stocked_sheet(test_session)
    repo = CatalogRepository(test_session)

    found = await repo.search_canonical_products("fanera", limit=20, require_offers=True)
    found_ids = {p.id for p in found}

    assert stocked_id in found_ids
    assert unstocked_id not in found_ids, "a sheet with no offer must not be offered"


@pytest.mark.asyncio
async def test_shop_search_still_sees_the_whole_catalogue(test_session: AsyncSession) -> None:
    """A shop uploading a price is creating the first offer for that product."""
    stocked_id, unstocked_id = await _catalogue_with_one_stocked_sheet(test_session)
    repo = CatalogRepository(test_session)

    found = await repo.search_canonical_products("fanera", limit=20)
    found_ids = {p.id for p in found}

    assert {stocked_id, unstocked_id} <= found_ids


@pytest.mark.asyncio
async def test_a_stale_offer_does_not_count_as_stock(test_session: AsyncSession) -> None:
    """Stale prices are excluded from quotes, so they must not gate a match either."""
    stocked_id, _ = await _catalogue_with_one_stocked_sheet(test_session)
    repo = CatalogRepository(test_session)

    offers = await test_session.execute(
        ShopProduct.__table__.update()
        .where(ShopProduct.canonical_id == stocked_id)
        .values(staleness_state="stale")
    )
    assert offers.rowcount == 1
    await test_session.flush()

    found = await repo.search_canonical_products("fanera", limit=20, require_offers=True)
    assert stocked_id not in {p.id for p in found}
