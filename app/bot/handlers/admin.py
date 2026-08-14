from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import esc
from app.bot.keyboards.inline import (
    get_admin_admins_keyboard,
    get_admin_back_keyboard,
    get_admin_panel_keyboard,
    get_district_keyboard,
)
from app.bot.states import AdminPanelStates, AdminShopStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.models.ops import UnmatchedQuery
from app.db.models.order import Order
from app.db.models.shop import Shop, ShopProduct
from app.db.models.user import User
from app.db.repositories.shop_repo import ShopRepository
from app.db.repositories.user_repo import UserRepository

router = Router(name="admin")


def is_admin(user: User) -> bool:
    return user.tg_id in settings.admin_tg_ids or user.role == "admin"


def is_super_admin(user: User) -> bool:
    return user.tg_id in settings.super_admin_tg_ids


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
        text_lines.append(f"• «{esc(q.raw_text)}» (norm: {esc(q.normalized)}) — {esc(q.status)}")

    await message.answer("\n".join(text_lines))


# ---------------------------------------------------------------------------
# Admin panel: shop onboarding (admins only)
# ---------------------------------------------------------------------------


@router.message(F.text.in_(["🛠 Admin panel", "🛠 Админ панел", "🛠 Админ-панель"]))
async def menu_admin_panel(message: Message, user: User, lang: str) -> None:
    if not is_admin(user):
        await message.answer(t("admin_only", lang=lang))
        return
    await message.answer(
        t("admin_panel_title", lang=lang),
        reply_markup=get_admin_panel_keyboard(lang=lang, is_super_admin=is_super_admin(user)),
    )


@router.callback_query(F.data == "adm:home")
async def cb_admin_home(callback: CallbackQuery, user: User, lang: str) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await callback.message.edit_text(
        t("admin_panel_title", lang=lang),
        reply_markup=get_admin_panel_keyboard(lang=lang, is_super_admin=is_super_admin(user)),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return

    users = await session.scalar(select(func.count(User.id)))
    shops = await session.scalar(select(func.count(Shop.id)).where(Shop.is_active.is_(True)))
    skus = await session.scalar(select(func.count(CanonicalProduct.id)))
    offers = await session.scalar(
        select(func.count(ShopProduct.id)).where(ShopProduct.is_active.is_(True))
    )
    orders = await session.scalar(select(func.count(Order.id)))
    gmv = await session.scalar(select(func.coalesce(func.sum(Order.grand_total_quoted), 0)))
    unmatched = await session.scalar(select(func.count(UnmatchedQuery.id)))

    await callback.message.edit_text(
        t(
            "adm_stats_body",
            lang=lang,
            users=users or 0,
            shops=shops or 0,
            skus=skus or 0,
            offers=offers or 0,
            orders=orders or 0,
            gmv=f"{gmv or 0:,.0f}",
            unmatched=unmatched or 0,
        ),
        reply_markup=get_admin_back_keyboard(lang=lang),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:shops")
async def cb_admin_shops(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return

    shop_repo = ShopRepository(session)
    shops = await shop_repo.list_active_shops()
    if not shops:
        await callback.message.edit_text(
            t("admin_shops_empty", lang=lang), reply_markup=get_admin_back_keyboard(lang=lang)
        )
        await callback.answer()
        return

    lines = [t("admin_shops_header", lang=lang, count=len(shops))]
    for shop in shops[:25]:
        owners = await shop_repo.list_shop_owners(shop.id)
        owner_ids = ", ".join(str(o.tg_id) for o in owners) or "—"
        lines.append(f"• <b>{shop.name}</b> (ID: {shop.id})\n  Egalari: {owner_ids}")
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=get_admin_back_keyboard(lang=lang)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:products")
async def cb_admin_products(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return

    stmt = (
        select(
            CanonicalProduct.name_uz,
            func.min(ShopProduct.price_per_pack),
            func.count(ShopProduct.id),
        )
        .outerjoin(
            ShopProduct,
            (ShopProduct.canonical_id == CanonicalProduct.id) & (ShopProduct.is_active.is_(True)),
        )
        .where(CanonicalProduct.is_active.is_(True))
        .group_by(CanonicalProduct.id, CanonicalProduct.name_uz)
        .order_by(CanonicalProduct.name_uz)
        .limit(25)
    )
    rows = (await session.execute(stmt)).all()

    lines = [t("adm_products_header", lang=lang, count=len(rows))]
    for name, min_price, offer_count in rows:
        price_str = f"{min_price:,.0f} so'm" if min_price is not None else "—"
        lines.append(f"• {esc(name)} — {price_str} ({offer_count} taklif)")
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=get_admin_back_keyboard(lang=lang)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:users")
async def cb_admin_users(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return

    user_repo = UserRepository(session)
    total = await session.scalar(select(func.count(User.id))) or 0
    by_role = await user_repo.count_by_role()
    recent = await user_repo.list_recent_users(limit=15)

    role_str = " · ".join(f"{role}: {count}" for role, count in sorted(by_role.items()))
    lines = [t("adm_users_header", lang=lang, total=total, by_role=role_str)]
    for u in recent:
        name = u.full_name or u.username or "—"
        lines.append(f"• {esc(name)} (<code>{u.tg_id}</code>) — {esc(u.role)}")
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=get_admin_back_keyboard(lang=lang)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:unmatched")
async def cb_admin_unmatched(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return

    stmt = select(UnmatchedQuery).order_by(UnmatchedQuery.occurrences.desc()).limit(15)
    queries = list((await session.execute(stmt)).scalars().all())
    if not queries:
        text = "🔍 Topilmagan so'rovlar mavjud emas."
    else:
        lines = ["🔍 <b>Eng ko'p topilmagan so'rovlar:</b>\n"]
        for q in queries:
            lines.append(f"• «{esc(q.raw_text)}» — {q.occurrences}x ({esc(q.status)})")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=get_admin_back_keyboard(lang=lang))
    await callback.answer()


@router.callback_query(F.data == "adm:add_shop")
async def cb_admin_add_shop(
    callback: CallbackQuery, user: User, state: FSMContext, lang: str
) -> None:
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(AdminShopStates.entering_name)
    await callback.message.answer(t("admin_shop_ask_name", lang=lang))
    await callback.answer()


# ── Admin management (super admins only) ──────────────────────────────


@router.callback_query(F.data == "adm:admins")
async def cb_admin_admins(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not isinstance(callback.message, Message):
        return
    if not is_super_admin(user):
        await callback.answer(t("adm_super_admin_only", lang=lang), show_alert=True)
        return

    user_repo = UserRepository(session)
    admins = await user_repo.list_admins()
    lines = [t("adm_admins_header", lang=lang)]
    for tg_id in settings.super_admin_tg_ids:
        lines.append(f"• <code>{tg_id}</code> — bosh admin")
    for adm in admins:
        if adm.tg_id in settings.super_admin_tg_ids:
            continue
        name = adm.full_name or adm.username or "—"
        lines.append(f"• {esc(name)} (<code>{adm.tg_id}</code>)")
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=get_admin_admins_keyboard(lang=lang)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:add_admin")
async def cb_admin_add_admin(
    callback: CallbackQuery, user: User, state: FSMContext, lang: str
) -> None:
    if not isinstance(callback.message, Message):
        return
    if not is_super_admin(user):
        await callback.answer(t("adm_super_admin_only", lang=lang), show_alert=True)
        return
    await state.set_state(AdminPanelStates.entering_admin_id)
    await callback.message.answer(t("adm_ask_admin_id", lang=lang))
    await callback.answer()


@router.message(AdminPanelStates.entering_admin_id, F.text)
async def admin_add_admin_id(
    message: Message, user: User, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    if not message.text or not is_super_admin(user):
        return
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer(t("admin_owner_invalid", lang=lang))
        return

    user_repo = UserRepository(session)
    promoted = await user_repo.set_role(int(raw), "admin")
    if promoted is None:
        await message.answer(t("adm_admin_not_found", lang=lang))
        return
    await session.commit()
    await state.clear()
    await message.answer(t("adm_admin_added", lang=lang, tg_id=raw))


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
