"""Who may manage the catalogue, and the one shop it is sold from.

QurBot is not a marketplace: every price is ours, and there is a single shop
row behind all of them. Every place that used to ask "does this account own
that shop?" now asks the two questions answered here instead -- is this an
admin, and which row is ours. Keeping both in one module means the rule
cannot drift between the bot, the web panel and the workers.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.shop import District, Shop
from app.db.models.user import User


def is_admin(user: User | None) -> bool:
    """Admins are the only accounts that manage products, prices and orders."""
    if user is None:
        return False
    return user.role == "admin" or user.tg_id in settings.admin_tg_ids


async def get_house_shop(session: AsyncSession) -> Shop | None:
    """Our shop row, created on first use.

    Created lazily rather than only by the seed so a fresh database is usable
    the moment an admin adds a first product. It still needs a district to
    hang off (the column is NOT NULL), so before districts are loaded there is
    nothing to create and the caller is told so with None.
    """
    stmt = select(Shop).where(Shop.name == settings.house_shop_name).order_by(Shop.id)
    shop = (await session.execute(stmt)).scalars().first()
    if shop is not None:
        if not shop.is_active:
            shop.is_active = True
            await session.flush()
        return shop

    district = (await session.execute(select(District).order_by(District.id))).scalars().first()
    if district is None:
        return None
    shop = Shop(
        name=settings.house_shop_name,
        phone=settings.house_shop_phone,
        district_id=district.id,
        address="Toshkent",
        is_active=True,
    )
    session.add(shop)
    await session.flush()
    return shop


async def shop_for_admin(user: User | None, session: AsyncSession) -> Shop | None:
    """The shop an account may act on: ours for an admin, nothing for anyone else."""
    if not is_admin(user):
        return None
    return await get_house_shop(session)


async def is_house_shop(session: AsyncSession, shop_id: int) -> bool:
    """Whether an id taken from a callback or URL names our shop.

    Ids arrive from the client, so a handler acting on an order part or an
    import batch re-checks that it belongs to the live shop rather than to a
    retired partner row that happens to still exist.
    """
    shop = await get_house_shop(session)
    return shop is not None and shop.id == shop_id
