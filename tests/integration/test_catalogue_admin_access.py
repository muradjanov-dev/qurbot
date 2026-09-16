"""Only admins manage the catalogue, and only on our one shop.

Callback data and URLs are chosen by the client, so a customer can type an
order-part, import-batch or product id by hand. These cover the checks that
stop that, and the rule that a retired partner shop's rows stay out of reach
even for an admin.
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import (
    _batch_belongs_to_user,
    _load_editable_product,
    _owns_shop,
    _row_belongs_to_user,
)
from app.core.config import settings
from app.db.models import District, ImportRow, Shop, ShopProduct, User
from app.db.repositories import ShopRepository
from app.services.house_shop import get_house_shop, is_admin, shop_for_admin


async def _district(session: AsyncSession) -> District:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()
    return district


async def _people(session: AsyncSession) -> tuple[User, User]:
    admin = User(tg_id=777, full_name="Admin", lang="uz_latn", role="admin")
    customer = User(tg_id=111, full_name="Mijoz", lang="uz_latn", role="customer")
    session.add_all([admin, customer])
    await session.flush()
    return admin, customer


def test_admin_is_decided_by_role_or_configured_id() -> None:
    configured = settings.admin_tg_ids[0]
    assert is_admin(User(tg_id=configured, role="customer")) is True
    assert is_admin(User(tg_id=1, role="admin")) is True
    assert is_admin(User(tg_id=1, role="customer")) is False
    assert is_admin(None) is False


@pytest.mark.asyncio
async def test_house_shop_is_created_once_and_reused(test_session: AsyncSession) -> None:
    await _district(test_session)

    first = await get_house_shop(test_session)
    second = await get_house_shop(test_session)

    assert first is not None and second is not None
    assert first.id == second.id
    assert first.name == settings.house_shop_name


@pytest.mark.asyncio
async def test_house_shop_needs_a_district_to_exist(test_session: AsyncSession) -> None:
    """Before districts are seeded there is nothing to hang the row off."""
    assert await get_house_shop(test_session) is None


@pytest.mark.asyncio
async def test_only_admins_get_a_shop_to_act_on(test_session: AsyncSession) -> None:
    await _district(test_session)
    admin, customer = await _people(test_session)

    assert await shop_for_admin(admin, test_session) is not None
    assert await shop_for_admin(customer, test_session) is None


@pytest.mark.asyncio
async def test_shop_ids_are_checked_against_our_shop(test_session: AsyncSession) -> None:
    district = await _district(test_session)
    admin, customer = await _people(test_session)
    house = await get_house_shop(test_session)
    assert house is not None

    retired = Shop(name="Eski hamkor", phone="+998900000002", district_id=district.id, address="B")
    retired.is_active = False
    test_session.add(retired)
    await test_session.flush()

    assert await _owns_shop(admin, test_session, house.id) is True
    assert await _owns_shop(admin, test_session, retired.id) is False
    assert await _owns_shop(customer, test_session, house.id) is False


@pytest.mark.asyncio
async def test_import_batch_and_row_are_admin_only(test_session: AsyncSession) -> None:
    await _district(test_session)
    admin, customer = await _people(test_session)
    house = await get_house_shop(test_session)
    assert house is not None

    batch = await ShopRepository(test_session).create_import_batch(
        house.id, "narxlar.xlsx", total_rows=1
    )
    row = ImportRow(batch_id=batch.id, row_no=1, raw_payload={"name": "Fanera", "price": "1"})
    test_session.add(row)
    await test_session.flush()

    assert await _batch_belongs_to_user(admin, test_session, batch.id) is True
    assert await _batch_belongs_to_user(customer, test_session, batch.id) is False
    assert await _row_belongs_to_user(admin, test_session, row.id) is True
    assert await _row_belongs_to_user(customer, test_session, row.id) is False

    # Ids that do not exist are refused rather than treated as permitted.
    assert await _batch_belongs_to_user(admin, test_session, 999999) is False
    assert await _row_belongs_to_user(admin, test_session, 999999) is False


@pytest.mark.asyncio
async def test_product_edit_is_admin_only(test_session: AsyncSession) -> None:
    """Product ids come from callback data, so editing must re-check the caller."""
    await _district(test_session)
    admin, customer = await _people(test_session)
    house = await get_house_shop(test_session)
    assert house is not None

    product = ShopProduct(
        shop_id=house.id,
        raw_name="Fanera 12 mm",
        raw_unit="dona",
        pack_size=Decimal("1"),
        price_per_pack=Decimal("159000"),
        price_per_base_unit=Decimal("159000"),
    )
    test_session.add(product)
    await test_session.flush()

    assert await _load_editable_product(admin, test_session, product.id) is not None
    assert await _load_editable_product(customer, test_session, product.id) is None
    assert await _load_editable_product(admin, test_session, 999999) is None
