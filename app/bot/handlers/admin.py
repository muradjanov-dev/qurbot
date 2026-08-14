from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import get_district_keyboard
from app.bot.states import AdminShopStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.models.ops import UnmatchedQuery
from app.db.models.order import Order
from app.db.models.shop import Shop
from app.db.models.user import User
from app.db.repositories.shop_repo import ShopRepository

router = Router(name="admin")


def is_admin(user: User) -> bool:
    return user.tg_id in settings.admin_tg_ids or user.role == "admin"


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


# ---------------------------------------------------------------------------
# Admin panel: shop onboarding (admins only)
# ---------------------------------------------------------------------------


@router.message(F.text.in_(["🛠 Admin panel", "🛠 Админ панел", "🛠 Админ-панель"]))
async def menu_admin_panel(message: Message, user: User, lang: str) -> None:
    if not is_admin(user):
        await message.answer(t("admin_only", lang=lang))
        return
    await message.answer(t("admin_panel_title", lang=lang))


@router.message(Command("add_shop"))
async def cmd_add_shop(message: Message, user: User, state: FSMContext, lang: str) -> None:
    if not is_admin(user):
        await message.answer(t("admin_only", lang=lang))
        return
    await state.set_state(AdminShopStates.entering_name)
    await message.answer(t("admin_shop_ask_name", lang=lang))


@router.message(AdminShopStates.entering_name, F.text)
async def admin_shop_name(message: Message, state: FSMContext, lang: str) -> None:
    if not message.text:
        return
    await state.update_data(shop_name=message.text.strip())
    await state.set_state(AdminShopStates.entering_phone)
    await message.answer(t("admin_shop_ask_phone", lang=lang))


@router.message(AdminShopStates.entering_phone, F.text)
async def admin_shop_phone(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    if not message.text:
        return
    await state.update_data(shop_phone=message.text.strip())
    await state.set_state(AdminShopStates.choosing_district)

    shop_repo = ShopRepository(session)
    districts = await shop_repo.list_districts()
    await message.answer(
        t("admin_shop_ask_district", lang=lang),
        reply_markup=get_district_keyboard(districts, lang=lang),
    )


@router.callback_query(F.data.startswith("set_district:"), AdminShopStates.choosing_district)
async def admin_shop_district(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    if not callback.data:
        return
    district_id = int(callback.data.split(":")[1])
    await state.update_data(shop_district_id=district_id)
    await state.set_state(AdminShopStates.entering_address)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("admin_shop_ask_address", lang=lang))
    await callback.answer()


@router.message(AdminShopStates.entering_address, F.text)
async def admin_shop_address(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    if not message.text:
        return
    data = await state.get_data()

    shop_repo = ShopRepository(session)
    shop = await shop_repo.create_shop(
        name=data["shop_name"],
        phone=data["shop_phone"],
        district_id=data["shop_district_id"],
        address=message.text.strip(),
    )
    await session.commit()

    await state.update_data(shop_id=shop.id, owner_count=0)
    await state.set_state(AdminShopStates.entering_owner_id)
    await message.answer(t("admin_shop_created", lang=lang, name=shop.name, shop_id=shop.id))
    await message.answer(t("admin_shop_ask_owner", lang=lang))


@router.message(AdminShopStates.entering_owner_id, Command("done"))
async def admin_shop_finish(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    data = await state.get_data()
    shop_repo = ShopRepository(session)
    shop = await shop_repo.get(data["shop_id"])
    await state.clear()
    await message.answer(
        t(
            "admin_shop_done",
            lang=lang,
            name=shop.name if shop else "-",
            count=data.get("owner_count", 0),
        )
    )


@router.message(AdminShopStates.entering_owner_id, F.text)
async def admin_shop_add_owner(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    if not message.text:
        return
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer(t("admin_owner_invalid", lang=lang))
        return

    data = await state.get_data()
    shop_repo = ShopRepository(session)
    await shop_repo.add_shop_owner(shop_id=data["shop_id"], tg_id=int(raw))

    # Promote an existing user account so the shop portal shows up for them.
    stmt = select(User).where(User.tg_id == int(raw))
    res = await session.execute(stmt)
    owner_user = res.scalars().first()
    if owner_user is not None and owner_user.role == "customer":
        owner_user.role = "shop_owner"
    await session.commit()

    await state.update_data(owner_count=data.get("owner_count", 0) + 1)
    await message.answer(t("admin_owner_added", lang=lang, tg_id=raw))


@router.message(Command("shops"))
async def cmd_list_shops(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    if not is_admin(user):
        await message.answer(t("admin_only", lang=lang))
        return

    shop_repo = ShopRepository(session)
    shops = await shop_repo.list_active_shops()
    if not shops:
        await message.answer(t("admin_shops_empty", lang=lang))
        return

    lines = [t("admin_shops_header", lang=lang, count=len(shops))]
    for shop in shops:
        owners = await shop_repo.list_shop_owners(shop.id)
        owner_ids = ", ".join(str(o.tg_id) for o in owners) or "—"
        lines.append(f"• <b>{shop.name}</b> (ID: {shop.id})\n  Egalari: {owner_ids}")
    await message.answer("\n".join(lines))
