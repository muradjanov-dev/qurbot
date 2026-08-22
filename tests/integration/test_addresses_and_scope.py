"""Saved delivery addresses, and the launch category allowlist."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category
from app.db.models.shop import District
from app.db.models.user import User
from app.db.repositories.address_repo import AddressRepository
from app.db.repositories.catalog_repo import CatalogRepository
from app.services.address_service import AddressService
from app.services.geocoding_service import GeocodingService


async def _fixture(session: AsyncSession) -> tuple[User, District, District]:
    chilonzor = District(
        region="Toshkent",
        name_uz="Chilonzor",
        name_ru="Чиланзар",
        centroid_lat=Decimal("41.2750"),
        centroid_lng=Decimal("69.2050"),
    )
    yunusobod = District(
        region="Toshkent",
        name_uz="Yunusobod",
        name_ru="Юнусабад",
        centroid_lat=Decimal("41.3670"),
        centroid_lng=Decimal("69.2890"),
    )
    session.add_all([chilonzor, yunusobod])
    await session.flush()

    user = User(tg_id=990001, full_name="Test Customer", lang="uz_latn")
    session.add(user)
    await session.flush()
    return user, chilonzor, yunusobod


def _service(session: AsyncSession, address: str | None) -> AddressService:
    geocoder = GeocodingService()
    geocoder.reverse_geocode = AsyncMock(return_value=address)  # type: ignore[method-assign]
    return AddressService(session, geocoder=geocoder)


# ── resolving a pin ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pin_resolves_to_address_and_district(test_session: AsyncSession) -> None:
    user, chilonzor, _ = await _fixture(test_session)
    service = _service(test_session, "Chilonzor tumani, Bunyodkor ko'chasi 12")

    resolved = await service.resolve(41.2760, 69.2060, lang="uz_latn")

    assert resolved.address_text == "Chilonzor tumani, Bunyodkor ko'chasi 12"
    assert resolved.district_id == chilonzor.id
    assert resolved.needs_manual_address is False
    assert resolved.outside_service_area is False


@pytest.mark.asyncio
async def test_geocoder_silence_falls_back_to_typing(test_session: AsyncSession) -> None:
    """A geocoder outage must not block an order -- the pin is still captured."""
    await _fixture(test_session)
    service = _service(test_session, None)

    resolved = await service.resolve(41.2760, 69.2060, lang="uz_latn")

    assert resolved.needs_manual_address is True
    assert resolved.lat == Decimal("41.276")
    assert resolved.district_id is not None, "district still resolves without an address"


@pytest.mark.asyncio
async def test_pin_far_outside_tashkent_has_no_district(test_session: AsyncSession) -> None:
    await _fixture(test_session)
    service = _service(test_session, "Samarqand")

    resolved = await service.resolve(39.6270, 66.9750, lang="uz_latn")

    assert resolved.outside_service_area is True
    assert resolved.district_id is None


# ── the address book ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_address_becomes_the_default(test_session: AsyncSession) -> None:
    user, chilonzor, _ = await _fixture(test_session)
    service = _service(test_session, "Bunyodkor 12")

    resolved = await service.resolve(41.2760, 69.2060, lang="uz_latn")
    address = await service.save(user, resolved, "Bunyodkor 12")
    await test_session.commit()

    assert address.is_default is True
    assert user.district_id == chilonzor.id, "the user's district follows their default address"


@pytest.mark.asyncio
async def test_several_addresses_are_kept_with_one_default(test_session: AsyncSession) -> None:
    """The whole point: a customer picks which site this order goes to."""
    user, _, yunusobod = await _fixture(test_session)
    service = _service(test_session, "Bunyodkor 12")

    home = await service.save(user, await service.resolve(41.2760, 69.2060, lang="uz_latn"), "Uy")
    site = await service.save(
        user, await service.resolve(41.3660, 69.2880, lang="uz_latn"), "Obyekt"
    )
    await test_session.commit()

    addresses = await service.list_for(user)
    assert len(addresses) == 2
    assert home.is_default is True
    assert site.is_default is False
    assert addresses[0].id == home.id, "the default sorts first for the picker"
    assert site.district_id == yunusobod.id


@pytest.mark.asyncio
async def test_switching_the_default_moves_it(test_session: AsyncSession) -> None:
    user, _, _ = await _fixture(test_session)
    service = _service(test_session, "Bunyodkor 12")
    repo = AddressRepository(test_session)

    home = await service.save(user, await service.resolve(41.276, 69.206, lang="uz_latn"), "Uy")
    site = await service.save(user, await service.resolve(41.366, 69.288, lang="uz_latn"), "Obyekt")
    await repo.set_default(user.id, site.id)
    await test_session.commit()

    assert (await repo.get(site.id)).is_default is True  # type: ignore[union-attr]
    assert (await repo.get(home.id)).is_default is False  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_deleting_the_default_promotes_another(test_session: AsyncSession) -> None:
    """A customer with addresses must always have one preselected at checkout."""
    user, _, _ = await _fixture(test_session)
    service = _service(test_session, "Bunyodkor 12")
    repo = AddressRepository(test_session)

    home = await service.save(user, await service.resolve(41.276, 69.206, lang="uz_latn"), "Uy")
    await service.save(user, await service.resolve(41.366, 69.288, lang="uz_latn"), "Obyekt")
    await repo.delete(user.id, home.id)
    await test_session.commit()

    remaining = await repo.list_for_user(user.id)
    assert len(remaining) == 1
    assert remaining[0].is_default is True


@pytest.mark.asyncio
async def test_another_users_address_cannot_be_touched(test_session: AsyncSession) -> None:
    user, _, _ = await _fixture(test_session)
    other = User(tg_id=990002, lang="uz_latn")
    test_session.add(other)
    await test_session.flush()

    service = _service(test_session, "Bunyodkor 12")
    mine = await service.save(user, await service.resolve(41.276, 69.206, lang="uz_latn"), "Uy")
    await test_session.commit()

    repo = AddressRepository(test_session)
    assert await repo.delete(other.id, mine.id) is False
    assert await repo.set_default(other.id, mine.id) is None


# ── launch catalogue scope ────────────────────────────────────────────────


# The allowlist is a launch setting that moves as suppliers are onboarded, so
# these tests take the stocked category from the config rather than naming one.
# What is being tested is that the filter applies, not which slug is in it.
_ALLOWED_SLUG = settings.enabled_category_slugs[0]


async def _catalog_fixture(session: AsyncSession) -> None:
    allowed = Category(slug=_ALLOWED_SLUG, name_uz="Sotuvda", name_ru="В продаже", sort_order=1)
    blocked = Category(
        slug="sement-va-qorishmalar", name_uz="Sement", name_ru="Цемент", sort_order=2
    )
    session.add_all([allowed, blocked])
    await session.flush()

    session.add_all(
        [
            CanonicalProduct(
                slug="taxta-50x100",
                name_uz="Taxta 50x100",
                name_uz_cyrl="Тахта 50х100",
                name_ru="Доска 50х100",
                category_id=allowed.id,
                base_unit_code="dona",
                attributes={},
                search_doc="taxta 50x100 doska",
                tier="standard",
                is_active=True,
            ),
            CanonicalProduct(
                slug="sement-m400",
                name_uz="Sement M400",
                name_uz_cyrl="Семент М400",
                name_ru="Цемент М400",
                category_id=blocked.id,
                base_unit_code="kg",
                attributes={},
                search_doc="sement m400 cement",
                tier="standard",
                is_active=True,
            ),
        ]
    )
    await session.flush()


@pytest.mark.asyncio
async def test_only_enabled_categories_are_browsable(test_session: AsyncSession) -> None:
    await _catalog_fixture(test_session)
    repo = CatalogRepository(test_session)

    slugs = {c.slug for c in await repo.list_root_categories()}

    assert _ALLOWED_SLUG in slugs
    assert "sement-va-qorishmalar" not in slugs, "a category we do not stock must not be offered"


@pytest.mark.asyncio
async def test_products_outside_the_scope_do_not_match(test_session: AsyncSession) -> None:
    """Quoting something we cannot source is worse than saying we don't carry it."""
    await _catalog_fixture(test_session)
    repo = CatalogRepository(test_session)

    assert await repo.search_canonical_products("sement") == []
    in_scope = await repo.search_canonical_products("taxta")
    assert [p.slug for p in in_scope] == ["taxta-50x100"]


@pytest.mark.asyncio
async def test_clearing_the_allowlist_restores_the_full_catalogue(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _catalog_fixture(test_session)
    monkeypatch.setattr(settings, "enabled_category_slugs", [])
    repo = CatalogRepository(test_session)

    assert len(await repo.list_root_categories()) == 2
    assert len(await repo.search_canonical_products("sement")) == 1


@pytest.mark.asyncio
async def test_admins_see_products_the_allowlist_hides(test_session: AsyncSession) -> None:
    """The allowlist governs what customers are offered, not what admins can see.

    An operator who cannot see the products they switched off has no way to
    check whether switching them off was right.
    """
    await _catalog_fixture(test_session)
    repo = CatalogRepository(test_session)

    # Customer-facing search is scoped ...
    assert await repo.search_canonical_products("sement") == []

    # ... the admin listing is not.
    rows, total = await repo.admin_list_products()
    slugs = {product.slug for product, _count, _price in rows}
    assert total == 2
    assert slugs == {"taxta-50x100", "sement-m400"}


@pytest.mark.asyncio
async def test_admin_product_search_and_paging(test_session: AsyncSession) -> None:
    await _catalog_fixture(test_session)
    repo = CatalogRepository(test_session)

    found, total = await repo.admin_list_products(search="sement")
    assert total == 1
    assert found[0][0].slug == "sement-m400"

    first_page, total_all = await repo.admin_list_products(offset=0, limit=1)
    second_page, _ = await repo.admin_list_products(offset=1, limit=1)
    assert total_all == 2
    assert len(first_page) == 1 and len(second_page) == 1
    assert first_page[0][0].slug != second_page[0][0].slug
