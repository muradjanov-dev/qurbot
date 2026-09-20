from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import esc, format_catalog_price
from app.bot.keyboards.inline import (
    get_admin_admins_keyboard,
    get_admin_back_keyboard,
    get_admin_panel_keyboard,
    get_admin_products_keyboard,
)
from app.bot.states import AdminPanelStates
from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.catalog import CanonicalProduct
from app.db.models.ops import UnmatchedQuery
from app.db.models.order import Order
from app.db.models.shop import ShopProduct
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.user_repo import UserRepository
from app.services.house_shop import is_admin

router = Router(name="admin")
logger = get_logger(__name__)


def is_super_admin(user: User) -> bool:
    return user.tg_id in settings.super_admin_tg_ids


@router.callback_query(F.data.startswith("admin_order:"))
async def callback_admin_order_decision(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    bot: Bot,
    lang: str,
) -> None:
    """Confirm or cancel an order after an operator calls the customer."""
    if not is_admin(user):
        await callback.answer(t("admin_only", lang=lang), show_alert=True)
        return

    try:
        _prefix, action, raw_order_id = (callback.data or "").split(":", 2)
        order_id = int(raw_order_id)
    except (TypeError, ValueError):
        await callback.answer("Noto'g'ri buyurtma tugmasi.", show_alert=True)
        return
    if action not in {"confirm", "cancel"}:
        await callback.answer("Noto'g'ri amal.", show_alert=True)
        return

    result = await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if order is None or order.is_test:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if order.status != "new":
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramAPIError:
                logger.warning("admin_order_markup_remove_failed", order_id=order.id)
        await callback.answer(
            f"Buyurtma allaqachon {order.status} holatida.",
            show_alert=True,
        )
        return

    customer = await session.get(User, order.user_id)
    if action == "confirm":
        order.status = "confirmed"
        admin_result = f"✅ Buyurtma #{order.id} tasdiqlandi."
        customer_key = "order_admin_confirmed_customer"
    else:
        order.status = "cancelled"
        order.cancel_reason = "Operator tomonidan bekor qilindi"
        admin_result = f"❌ Buyurtma #{order.id} bekor qilindi."
        customer_key = "order_admin_cancelled_customer"
    await session.commit()

    await callback.answer(admin_result)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            logger.warning("admin_order_markup_remove_failed", order_id=order.id)
        await callback.message.answer(admin_result)

    if customer is not None and customer.tg_id is not None:
        try:
            await bot.send_message(
                customer.tg_id,
                t(customer_key, lang=customer.lang, order_id=order.id),
            )
        except TelegramAPIError as exc:
            logger.warning(
                "admin_order_customer_notify_failed",
                order_id=order.id,
                customer_tg_id=customer.tg_id,
                error=str(exc),
            )


@router.message(Command("admin"))
async def cmd_admin_stats(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not is_admin(user):
        return

    # Aggregate counts
    user_count = await session.scalar(select(func.count(User.id)))
    order_count = await session.scalar(select(func.count(Order.id)).where(Order.is_test.is_(False)))
    sku_count = await session.scalar(select(func.count(CanonicalProduct.id)))
    unmatched_count = await session.scalar(select(func.count(UnmatchedQuery.id)))

    stats_text = (
        "📊 <b>QurBot Admin Paneli</b>\n\n"
        f"• Foydalanuvchilar: <b>{user_count}</b>\n"
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
    if not is_admin(user):
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
# Admin panel (admins only)
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
    skus = await session.scalar(select(func.count(CanonicalProduct.id)))
    offers = await session.scalar(
        select(func.count(ShopProduct.id)).where(ShopProduct.is_active.is_(True))
    )
    orders = await session.scalar(select(func.count(Order.id)).where(Order.is_test.is_(False)))
    gmv = await session.scalar(
        select(func.coalesce(func.sum(Order.grand_total_quoted), 0)).where(Order.is_test.is_(False))
    )
    unmatched = await session.scalar(select(func.count(UnmatchedQuery.id)))

    await callback.message.edit_text(
        t(
            "adm_stats_body",
            lang=lang,
            users=users or 0,
            skus=skus or 0,
            offers=offers or 0,
            orders=orders or 0,
            gmv=f"{gmv or 0:,.0f}",
            unmatched=unmatched or 0,
        ),
        reply_markup=get_admin_back_keyboard(lang=lang),
    )
    await callback.answer()


ADMIN_PRODUCTS_PAGE_SIZE = 20


@router.callback_query(F.data == "adm:products")
@router.callback_query(F.data.startswith("adm:products:"))
async def cb_admin_products(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    """The whole catalogue, a page at a time.

    Shows every product regardless of the customer-facing category allowlist:
    that setting decides what is offered, not what an operator may inspect.
    """
    if not is_admin(user) or not isinstance(callback.message, Message):
        await callback.answer()
        return

    page = 0
    if callback.data and callback.data.count(":") == 2:
        try:
            page = max(0, int(callback.data.rsplit(":", 1)[1]))
        except ValueError:
            page = 0

    repo = CatalogRepository(session)
    rows, total = await repo.admin_list_products(
        offset=page * ADMIN_PRODUCTS_PAGE_SIZE, limit=ADMIN_PRODUCTS_PAGE_SIZE
    )
    pages = max(1, (total + ADMIN_PRODUCTS_PAGE_SIZE - 1) // ADMIN_PRODUCTS_PAGE_SIZE)

    lines = [t("adm_products_header", lang=lang, count=total)]
    for product, offer_count, min_price in rows:
        # An operator looking at the catalogue needs to know both what a row
        # costs and who put it there -- a price with no provenance is not
        # something they can act on.
        price_str = format_catalog_price(min_price, product.reference_price, lang=lang)
        origin = product.source_ref or product.source
        lines.append(
            f"• {esc(product.name_uz)} — <b>{price_str}</b> "
            f"({offer_count} taklif · {esc(origin)})"
        )
    lines.append(f"\n{t('price_reference_hint', lang=lang)}")
    lines.append(f"{page + 1} / {pages}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=get_admin_products_keyboard(page=page, pages=pages, lang=lang),
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
