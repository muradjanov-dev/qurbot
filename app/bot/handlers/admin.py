from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct
from app.db.models.ops import UnmatchedQuery
from app.db.models.order import Order
from app.db.models.shop import Shop
from app.db.models.user import User

router = Router(name="admin")


@router.message(Command("admin"))
async def cmd_admin_stats(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if user.tg_id not in settings.admin_tg_ids and user.role != "admin":
        return

    # Aggregate counts
    user_count = await session.scalar(select(func.count(User.id)))
    shop_count = await session.scalar(select(func.count(Shop.id)))
    order_count = await session.scalar(select(func.count(Order.id)))
    sku_count = await session.scalar(select(func.count(CanonicalProduct.id)))
    unmatched_count = await session.scalar(select(func.count(UnmatchedQuery.id)))

    stats_text = (
        "📊 <b>QurBot Admin Paneli</b>\n\n"
        f"• Foydalanuvchilar: <b>{user_count}</b>\n"
        f"• Hamkor do'konlar: <b>{shop_count}</b>\n"
        f"• Buyurtmalar: <b>{order_count}</b>\n"
        f"• Katalogdagi SKU: <b>{sku_count}</b>\n"
        f"• Topilmagan so'rovlar: <b>{unmatched_count}</b>\n\n"
        "Buyruqlar: /unmatched"
    )
    await message.answer(stats_text)


@router.message(Command("unmatched"))
async def cmd_unmatched_queries(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if user.tg_id not in settings.admin_tg_ids and user.role != "admin":
        return

    stmt = select(UnmatchedQuery).order_by(UnmatchedQuery.created_at.desc()).limit(10)
    res = await session.execute(stmt)
    queries = list(res.scalars().all())

    if not queries:
        await message.answer("Topilmagan so'rovlar mavjud emas.")
        return

    text_lines = ["🔍 <b>So'nggi topilmagan so'rovlar:</b>\n"]
    for q in queries:
        text_lines.append(f"• «{q.raw_text}» (norm: {q.normalized}) — {q.status}")

    await message.answer("\n".join(text_lines))
