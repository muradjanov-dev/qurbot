"""Migration 0015: one shop, and nobody left holding the shop-owner role.

What makes it safe is that it is narrow. Our shop and its prices keep quoting;
every other shop and offer is switched off rather than deleted, so order history
that points at them keeps resolving.
"""

import importlib.util
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User

_MIGRATION = pathlib.Path("migrations/versions/0015_single_house_shop.py")


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("single_house_shop", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _offer(shop_id: int) -> ShopProduct:
    return ShopProduct(
        shop_id=shop_id,
        raw_name="Fanera 12 mm",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("159000"),
        price_per_base_unit=Decimal("159000"),
        is_active=True,
    )


async def _market(session: AsyncSession) -> tuple[Shop, Shop, User, User]:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()

    house = Shop(name="QurBot", phone="+998935394994", district_id=district.id, address="A")
    partner = Shop(name="Hamkor", phone="+998900000001", district_id=district.id, address="B")
    session.add_all([house, partner])
    await session.flush()
    session.add_all([_offer(house.id), _offer(partner.id)])

    owner = User(tg_id=3001, full_name="Do'kon egasi", role="shop_owner")
    admin = User(tg_id=3002, full_name="Admin", role="admin")
    session.add_all([owner, admin])
    await session.flush()
    return house, partner, owner, admin


def test_the_migration_names_the_shop_the_app_uses() -> None:
    """Inlined on purpose, so it must still agree with the setting it mirrors."""
    assert settings.house_shop_name == _load_migration().HOUSE_SHOP_NAME


@pytest.mark.asyncio
async def test_partner_shops_retire_and_ours_keeps_quoting(test_session: AsyncSession) -> None:
    house, partner, owner, admin = await _market(test_session)
    migration = _load_migration()

    connection = await test_session.connection()
    offers, shops, users = await connection.run_sync(migration.retire_partner_shops)
    assert (offers, shops, users) == (1, 1, 1)

    for row in (house, partner, owner, admin):
        await test_session.refresh(row)
    assert house.is_active is True
    assert partner.is_active is False
    assert owner.role == "customer"
    assert admin.role == "admin"

    active_by_shop = dict(
        (await test_session.execute(select(ShopProduct.shop_id, ShopProduct.is_active))).all()
    )
    assert active_by_shop == {house.id: True, partner.id: False}


@pytest.mark.asyncio
async def test_running_it_twice_changes_nothing_more(test_session: AsyncSession) -> None:
    await _market(test_session)
    migration = _load_migration()
    connection = await test_session.connection()

    await connection.run_sync(migration.retire_partner_shops)
    assert await connection.run_sync(migration.retire_partner_shops) == (0, 0, 0)
