import asyncio
from decimal import Decimal
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import esc, format_qty
from app.bot.keyboards.inline import (
    get_basket_actions_keyboard,
    get_order_confirm_keyboard,
    get_quote_carousel_keyboard,
)
from app.bot.keyboards.reply import get_main_menu_keyboard
from app.bot.states import BasketStates, OrderCheckoutStates
from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.order import Order, OrderItem, OrderShopPart
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.order_repo import OrderRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.optimizer.models import BasketItemQuery, OptimizationStrategy, QuoteVariant
from app.services.catalog_service import CatalogService
from app.services.pdf_service import generate_quote_pdf
from app.services.quote_service import QuoteService

logger = get_logger(__name__)

router = Router(name="customer")

# Reply-keyboard buttons reach the bot as ordinary text messages, so the
# free-text basket handler has to be able to tell them apart from a real
# product list. Keyed on the leading emoji, which every menu label carries.
_MENU_BUTTON_PREFIXES = ("🧾", "📦", "🔍", "🛒", "🏪", "⚙️", "👤", "⬅️", "➕", "🛠")


@router.message(F.text.in_(["🧾 Ro'yxat yuborish", "🧾 Рўйхат юбориш", "🧾 Отправить список"]))
async def menu_send_list(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(BasketStates.waiting_for_basket_text)
    await message.answer(t("prompt_send_basket", lang=lang))


def _not_a_menu_button(message: Message) -> bool:
    """True when this text is free-form input rather than a menu tap.

    This MUST be a filter, not an early return inside the handler: a handler
    whose filters pass is considered to have handled the update, so returning
    early still stops propagation and the button's real handler -- which lives
    in a router registered later -- never runs.
    """
    text = message.text
    if not text:
        return False
    return not text.startswith(_MENU_BUTTON_PREFIXES)


@router.message(
    StateFilter(None, BasketStates.waiting_for_basket_text, BasketStates.viewing_quotes),
    F.text & ~F.text.startswith("/"),
    _not_a_menu_button,
)
async def handle_basket_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
) -> None:
    if not message.text:
        return
    await _process_basket_input(message, state, session, lang, message.text, existing_lines=None)


@router.message(BasketStates.adding_item)
async def handle_add_item_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
) -> None:
    if not message.text:
        return
    data = await state.get_data()
    existing_lines: list[dict[str, Any]] = data.get("basket_lines", [])
    await _process_basket_input(
        message, state, session, lang, message.text, existing_lines=existing_lines
    )


async def _process_basket_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
    raw_text: str,
    existing_lines: list[dict[str, Any]] | None,
) -> None:
    """Parse+match `raw_text` and render the basket table, optionally merging
    onto `existing_lines` (used when the user is adding items to an existing
    basket rather than starting a fresh one)."""
    # 1. Immediate acknowledgement message according to SPEC §9
    status_msg = await message.answer(t("parsing_in_progress", lang=lang))

    # 2. Parse and match lines
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    catalog_service = CatalogService(catalog_repo, ops_repo)

    parsed_results = await catalog_service.parse_and_match_basket(raw_text)

    if not parsed_results or all(line.needs_review for line, _ in parsed_results):
        # The parser found no explicit "qty + unit" pattern on any line -- the
        # parser still fabricates a qty=1 pseudo-line for plain text (greetings,
        # questions), so `not parsed_results` alone doesn't catch that; checking
        # `needs_review` (set when qty/unit weren't explicitly found) does. A
        # message with at least one real "10 dona X"-shaped line still reaches
        # the parse table below, even if that product isn't in the catalog --
        # Stage 4 already handles that per-line.
        await status_msg.edit_text(t("basket_not_understood", lang=lang))
        if existing_lines:
            await state.set_state(BasketStates.viewing_quotes)
        return

    # 3. Serialize new lines, continuing line numbering after any existing ones
    start_no = max((item["line_no"] for item in existing_lines), default=0) if existing_lines else 0
    new_lines: list[dict[str, Any]] = []
    for offset, (line, decision) in enumerate(parsed_results, start=1):
        cand_data = []
        if decision.candidates:
            for c in decision.candidates:
                cand_data.append(
                    {
                        "canonical_id": c.canonical_id,
                        "name_uz": c.name_uz,
                        "score": c.score,
                    }
                )

        new_lines.append(
            {
                "line_no": start_no + offset,
                "raw_text": line.raw_text,
                "parsed_name": line.parsed_name,
                "qty": str(line.qty),
                "unit_code": line.unit_code or "dona",
                "status": decision.status,
                "method": decision.method,
                "confidence": decision.confidence,
                "canonical_id": decision.canonical_id,
                "canonical_name": (
                    decision.candidates[0].name_uz if decision.candidates else line.parsed_name
                ),
                "candidates": cand_data,
            }
        )

    # 3b. Attach a reference price to each candidate so ambiguous-line pickers
    # let the user tell products apart by price, not just name.
    ask_user_canonical_ids = {
        cand["canonical_id"]
        for item in new_lines
        if item["status"] == "ask_user"
        for cand in item["candidates"]
    }
    if ask_user_canonical_ids:
        shop_repo = ShopRepository(session)
        offers = await shop_repo.get_active_offers_for_canonicals(list(ask_user_canonical_ids))
        min_price_by_canonical: dict[int, Decimal] = {}
        for offer in offers:
            if offer.canonical_id is not None and offer.canonical_id not in min_price_by_canonical:
                min_price_by_canonical[offer.canonical_id] = offer.price_per_pack
        for item in new_lines:
            if item["status"] == "ask_user":
                for cand in item["candidates"]:
                    price = min_price_by_canonical.get(cand["canonical_id"])
                    cand["min_price"] = f"{price:,.0f}" if price is not None else None

    serialized_lines = (existing_lines or []) + new_lines

    await state.set_state(BasketStates.viewing_quotes)

    # 4. Render parse table -- edit the existing table message when merging
    # (add_item), otherwise this status message becomes the table.
    table_text = _format_parse_table(serialized_lines, lang=lang)
    data = await state.get_data()
    table_chat_id = data.get("table_chat_id")
    table_message_id = data.get("table_message_id")

    if existing_lines and table_chat_id and table_message_id:
        await message.bot.edit_message_text(  # type: ignore[union-attr]
            table_text,
            chat_id=table_chat_id,
            message_id=table_message_id,
            reply_markup=get_basket_actions_keyboard(lang=lang),
        )
        await status_msg.delete()
    else:
        await status_msg.edit_text(
            table_text,
            reply_markup=get_basket_actions_keyboard(lang=lang),
        )
        table_chat_id = status_msg.chat.id
        table_message_id = status_msg.message_id

    await state.update_data(
        basket_lines=serialized_lines,
        table_chat_id=table_chat_id,
        table_message_id=table_message_id,
    )

    # 5. For every newly-ambiguous line, ask which specific product was meant
    for item in new_lines:
        if item["status"] == "ask_user" and item["candidates"]:
            await message.answer(
                t("choose_candidate_prompt", lang=lang, name=item["parsed_name"]),
                reply_markup=_build_candidate_picker_keyboard(item["line_no"], item["candidates"]),
            )


@router.callback_query(F.data.startswith("pick_cand:"))
async def callback_pick_candidate(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    lang: str,
) -> None:
    if not callback.data:
        return
    parts = callback.data.split(":")
    line_no = int(parts[1])
    canonical_id = int(parts[2])

    data = await state.get_data()
    lines: list[dict[str, Any]] = data.get("basket_lines", [])

    chosen_name = ""
    for line in lines:
        if line["line_no"] == line_no:
            line["status"] = "auto_accept"
            line["canonical_id"] = canonical_id
            for c in line.get("candidates", []):
                if c["canonical_id"] == canonical_id:
                    line["canonical_name"] = c["name_uz"]
                    chosen_name = c["name_uz"]
                    break

    await state.update_data(basket_lines=lines)

    # Confirm on the picker message itself (drop its buttons)...
    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("candidate_selected", lang=lang, name=chosen_name))

    # ...and refresh the main basket table separately, since a message can
    # only carry one ambiguous-line picker but a basket can have several.
    table_chat_id = data.get("table_chat_id")
    table_message_id = data.get("table_message_id")
    if table_chat_id and table_message_id:
        table_text = _format_parse_table(lines, lang=lang)
        await bot.edit_message_text(
            table_text,
            chat_id=table_chat_id,
            message_id=table_message_id,
            reply_markup=get_basket_actions_keyboard(lang=lang),
        )
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    lang: str,
) -> None:
    await state.clear()
    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    if isinstance(callback.message, Message):
        await callback.message.answer(
            t("action_cancelled", lang=lang),
            reply_markup=get_main_menu_keyboard(
                lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "clear_basket")
async def callback_clear_basket(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    await state.update_data(basket_lines=[])
    await state.set_state(BasketStates.waiting_for_basket_text)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("prompt_send_basket", lang=lang))
    await callback.answer()


@router.callback_query(F.data == "edit_basket")
async def callback_edit_basket(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    data = await state.get_data()
    lines: list[dict[str, Any]] = data.get("basket_lines", [])
    current_list = "\n".join(f"- {item['raw_text']}" for item in lines) or "-"

    await state.set_state(BasketStates.waiting_for_basket_text)
    if isinstance(callback.message, Message):
        await callback.message.answer(t("prompt_edit_basket", lang=lang, current_list=current_list))
    await callback.answer()


@router.callback_query(F.data == "add_item")
async def callback_add_item(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    await state.set_state(BasketStates.adding_item)
    if isinstance(callback.message, Message):
        await callback.message.answer(t("prompt_add_item", lang=lang))
    await callback.answer()


@router.callback_query(F.data == "calculate_quotes")
async def callback_calculate_quotes(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
) -> None:
    data = await state.get_data()
    lines: list[dict[str, Any]] = data.get("basket_lines", [])
    if not lines:
        if isinstance(callback.message, Message):
            await callback.message.answer(t("prompt_send_basket", lang=lang))
        return

    # Build basket items from accepted lines
    basket_items: list[BasketItemQuery] = []
    for line in lines:
        if line.get("canonical_id"):
            basket_items.append(
                BasketItemQuery(
                    line_no=line["line_no"],
                    canonical_id=line["canonical_id"],
                    name_uz=line.get("canonical_name", line["parsed_name"]),
                    needed_qty=Decimal(line["qty"]),
                    unit_code=line["unit_code"],
                )
            )

    if not basket_items:
        if isinstance(callback.message, Message):
            await callback.message.answer("Hech qanday mahsulot tasdiqlanmagan.")
        return

    shop_repo = ShopRepository(session)
    catalog_repo = CatalogRepository(session)
    quote_service = QuoteService(shop_repo, catalog_repo)

    result = await quote_service.optimize_basket(
        basket_items=basket_items,
        district_id=user.district_id,
    )

    if not result.deduplicated_variants:
        if isinstance(callback.message, Message):
            await callback.message.answer("Do'konlarda ushbu mahsulotlar topilmadi.")
        return

    # Cache variants in state
    cached_variants = []
    for v in result.deduplicated_variants:
        cached_variants.append(_serialize_variant(v))

    await state.update_data(quotes=cached_variants, current_quote_idx=0)

    # Render first variant
    variant_card_text = _format_quote_card(result.deduplicated_variants[0], lang=lang)
    if isinstance(callback.message, Message):
        await _safe_edit_text(
            callback.message,
            variant_card_text,
            reply_markup=get_quote_carousel_keyboard(
                current_index=0,
                total_variants=len(result.deduplicated_variants),
                lang=lang,
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("nav_quote:"))
async def callback_nav_quote(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    if not callback.data:
        return
    idx = int(callback.data.split(":")[1])

    data = await state.get_data()
    raw_quotes: list[dict[str, Any]] = data.get("quotes", [])
    if not raw_quotes or idx >= len(raw_quotes):
        return

    await state.update_data(current_quote_idx=idx)
    variant = _deserialize_variant(raw_quotes[idx])
    variant_card_text = _format_quote_card(variant, lang=lang)

    if isinstance(callback.message, Message):
        await _safe_edit_text(
            callback.message,
            variant_card_text,
            reply_markup=get_quote_carousel_keyboard(
                current_index=idx,
                total_variants=len(raw_quotes),
                lang=lang,
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("pdf_quote:"))
async def callback_pdf_quote(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    if not callback.data:
        return
    idx = int(callback.data.split(":")[1])

    data = await state.get_data()
    raw_quotes: list[dict[str, Any]] = data.get("quotes", [])
    if not raw_quotes or idx >= len(raw_quotes):
        await callback.answer()
        return

    await callback.answer(t("pdf_generating", lang=lang))
    variant = _deserialize_variant(raw_quotes[idx])
    pdf_bytes = await asyncio.to_thread(generate_quote_pdf, variant)

    if isinstance(callback.message, Message):
        await callback.message.answer_document(
            BufferedInputFile(pdf_bytes, filename=f"qurbot_taklif_{idx + 1}.pdf"),
        )


@router.callback_query(F.data.startswith("select_quote:"))
async def callback_select_quote(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    lang: str,
) -> None:
    if not callback.data:
        return
    idx = int(callback.data.split(":")[1])
    await state.update_data(selected_quote_idx=idx)

    data = await state.get_data()
    contact_phone = data.get("contact_phone")

    # Check if user has phone
    if not contact_phone:
        await state.set_state(OrderCheckoutStates.confirming_phone)
        if isinstance(callback.message, Message):
            await callback.message.answer(t("prompt_checkout_phone", lang=lang))
    else:
        await state.set_state(OrderCheckoutStates.entering_address)
        if isinstance(callback.message, Message):
            await callback.message.answer(t("prompt_checkout_address", lang=lang))


@router.message(OrderCheckoutStates.confirming_phone)
async def checkout_phone(message: Message, state: FSMContext, lang: str) -> None:
    if message.text:
        await state.update_data(contact_phone=message.text.strip())

    await state.set_state(OrderCheckoutStates.entering_address)
    await message.answer(t("prompt_checkout_address", lang=lang))


@router.message(OrderCheckoutStates.entering_address)
async def checkout_address(message: Message, state: FSMContext, lang: str) -> None:
    if not message.text:
        return
    await state.update_data(delivery_address=message.text.strip())
    await state.set_state(OrderCheckoutStates.entering_comment)
    await message.answer(t("prompt_checkout_comment", lang=lang))


@router.message(OrderCheckoutStates.entering_comment)
async def checkout_comment(
    message: Message,
    state: FSMContext,
    lang: str,
) -> None:
    comment = message.text.strip() if message.text and message.text.lower() != "yo'q" else None
    await state.update_data(order_comment=comment)
    data = await state.get_data()

    address = data.get("delivery_address", "Toshkent shahri")
    phone = data.get("contact_phone", "+998900000000")
    raw_quotes = data.get("quotes", [])
    selected_idx = data.get("selected_quote_idx", 0)

    if not raw_quotes:
        await message.answer(t("error_generic", lang=lang))
        return

    variant = _deserialize_variant(raw_quotes[selected_idx])

    await state.set_state(OrderCheckoutStates.confirming_order)

    summary = t(
        "order_confirm_prompt",
        lang=lang,
        phone=phone,
        address=address,
        comment=comment or t("comment_none", lang=lang),
    )
    quote_card = _format_quote_card(variant, lang=lang)
    question = t("order_confirm_question", lang=lang)
    await message.answer(
        f"{summary}\n{quote_card}\n\n{question}",
        reply_markup=get_order_confirm_keyboard(lang=lang),
    )


@router.callback_query(F.data == "confirm_order")
async def callback_confirm_order(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    bot: Bot,
    lang: str,
) -> None:
    data = await state.get_data()

    address = data.get("delivery_address", "Toshkent shahri")
    phone = data.get("contact_phone", "+998900000000")
    comment = data.get("order_comment")
    raw_quotes = data.get("quotes", [])
    selected_idx = data.get("selected_quote_idx", 0)

    if not raw_quotes:
        if isinstance(callback.message, Message):
            await callback.message.answer(t("error_generic", lang=lang))
        await callback.answer()
        return

    variant = _deserialize_variant(raw_quotes[selected_idx])

    # Ensure a Basket exists in DB
    from app.db.models.order import Basket, Quote

    basket = Basket(
        user_id=user.id,
        raw_text="Customer basket",
        status="ordered",
    )
    session.add(basket)
    await session.flush()

    quote = Quote(
        basket_id=basket.id,
        strategy=variant.strategy_labels[0].value if variant.strategy_labels else "cheapest",
        items_total=variant.items_total_uzs,
        delivery_total=variant.delivery_total_uzs,
        grand_total=variant.grand_total_uzs,
        coverage_pct=Decimal(str(variant.coverage_pct)),
        shop_count=len(variant.shop_groups),
        eta_hours=variant.max_eta_hours,
    )
    session.add(quote)
    await session.flush()

    # Create Order in DB
    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        status="new",
        contact_phone=phone,
        delivery_address=address,
        grand_total_quoted=variant.grand_total_uzs,
        comment=comment,
    )
    session.add(order)
    await session.flush()

    # Create OrderShopParts and OrderItems
    shop_parts: list[tuple[OrderShopPart, Any]] = []
    for g in variant.shop_groups:
        part = OrderShopPart(
            order_id=order.id,
            shop_id=g.shop_id,
            subtotal=g.subtotal_uzs,
            delivery_fee=g.delivery_fee_uzs,
            status="new",
            shop_response="pending",
        )
        session.add(part)
        await session.flush()
        shop_parts.append((part, g))

        for line in g.lines:
            item = OrderItem(
                order_shop_part_id=part.id,
                canonical_id=line.canonical_id,
                shop_product_id=line.offer_id,
                qty=line.billed_qty,
                unit_code=line.pack_unit,
                unit_price_quoted=line.unit_price_uzs,
                line_total=line.line_cost_uzs,
            )
            session.add(item)

    await session.commit()
    await state.clear()

    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            t(
                "order_created_success",
                lang=lang,
                order_id=order.id,
                total=f"{order.grand_total_quoted:,.0f}",
            ),
        )
        await callback.message.answer(
            t("welcome_done", lang=lang),
            reply_markup=get_main_menu_keyboard(
                lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
            ),
        )
    await callback.answer()

    await _notify_shops_and_admins_of_order(bot, session, order, shop_parts, user, phone, address)


@router.message(F.text.in_(["📦 Buyurtmalarim", "📦 Буюртмаларим", "📦 Мои заказы"]))
async def menu_my_orders(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    order_repo = OrderRepository(session)
    orders = await order_repo.get_customer_orders(user.id)

    if not orders:
        await message.answer("Sizda hali buyurtmalar mavjud emas.")
        return

    text_lines = ["📦 <b>Sizning buyurtmalaringiz:</b>\n"]
    for o in orders[:5]:
        text_lines.append(
            f"• <b>#{o.id}</b> — {o.grand_total_quoted:,.0f} so'm ({o.status})\n"
            f"  Manzil: {o.delivery_address}"
        )
    await message.answer("\n\n".join(text_lines))


# -----------------------------------------------------------------------------
# Formatting Helpers
# -----------------------------------------------------------------------------


async def _notify_shops_and_admins_of_order(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    shop_parts: list[tuple[OrderShopPart, Any]],
    user: User,
    phone: str,
    address: str,
) -> None:
    """Tell each shop owner their part of the order, and admins the whole thing.

    Best-effort: a shop with no owner_tg_id on file, or a failed send, is
    logged and skipped rather than blocking the rest -- the order itself is
    already committed by the time this runs.
    """
    shop_repo = ShopRepository(session)
    customer_name = user.full_name or str(user.tg_id)

    for part, group in shop_parts:
        shop = await shop_repo.get(part.shop_id)
        if not shop or not shop.owner_tg_id:
            continue
        lines_str = "\n".join(
            f"• {esc(line.product_name)} × {format_qty(line.billed_qty)} {esc(line.pack_unit)}"
            for line in group.lines
        )
        text = (
            f"🆕 <b>Yangi buyurtma #{order.id}</b>\n\n"
            f"{lines_str}\n\n"
            f"Jami: <b>{part.subtotal:,.0f} so'm</b> + dostavka {part.delivery_fee:,.0f} so'm\n\n"
            f"👤 Mijoz: {customer_name}\n"
            f"📞 Tel: {phone}\n"
            f"📍 Manzil: {esc(address)}"
        )
        try:
            await bot.send_message(shop.owner_tg_id, text)
        except TelegramAPIError as exc:
            logger.warning("shop_order_notify_failed", shop_id=shop.id, error=str(exc))

    admin_text = (
        f"📦 <b>Yangi buyurtma #{order.id}</b>\n\n"
        f"Mijoz: {customer_name}\n"
        f"Tel: {phone}\n"
        f"Manzil: {address}\n"
        f"Jami: {order.grand_total_quoted:,.0f} so'm\n"
        f"Do'konlar soni: {len(shop_parts)}"
    )
    for admin_id in settings.admin_tg_ids:
        try:
            await bot.send_message(admin_id, admin_text)
        except TelegramAPIError as exc:
            logger.warning("admin_order_notify_failed", admin_id=admin_id, error=str(exc))


async def _safe_edit_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """edit_text, ignoring Telegram's "message is not modified" error.

    Recalculating/navigating to a quote that renders identically to what's
    already on screen (e.g. a single-shop-only variant, or re-running the
    same deterministic optimization) is a no-op from Telegram's point of
    view and it rejects the edit outright -- that's not a real failure.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def _build_candidate_picker_keyboard(
    line_no: int, candidates: list[dict[str, Any]]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cand in candidates[:3]:
        label = str(cand["name_uz"])
        if cand.get("min_price"):
            label = f"{label} — {cand['min_price']} so'm"
        builder.button(
            text=label,
            callback_data=f"pick_cand:{line_no}:{cand['canonical_id']}",
        )
    builder.adjust(1)
    return builder.as_markup()


def _format_parse_table(lines: list[dict[str, Any]], lang: str) -> str:
    count = len(lines)
    header = t("basket_parsed_header", lang=lang, count=count)
    body_lines = []

    for item in lines:
        num = item["line_no"]
        qty = item["qty"]
        unit = item["unit_code"]
        st = item["status"]

        if st == "auto_accept":
            name = item.get("canonical_name", item["parsed_name"])
            body_lines.append(f"{num}. ✅ <b>{esc(name)}</b> — {esc(qty)} {esc(unit)}")
        elif st == "ask_user":
            name = item["parsed_name"]
            body_lines.append(
                f"{num}. ⚠️ <i>{esc(name)}</i> — {esc(qty)} {esc(unit)}" "  ← <i>turini tanlang</i>"
            )
        elif item.get("method") == "invalid_qty":
            raw = item["raw_text"]
            body_lines.append(f"{num}. ❌ «{esc(raw)}» — <i>{t('qty_out_of_range', lang=lang)}</i>")
        else:
            raw = item["raw_text"]
            body_lines.append(f"{num}. ❌ «{esc(raw)}» — <i>katalogda topilmadi</i>")

    return header + "\n" + "\n".join(body_lines)


def _format_quote_card(variant: QuoteVariant, lang: str) -> str:
    # Header badge
    strat = (
        variant.strategy_labels[0]
        if variant.strategy_labels
        else OptimizationStrategy.CHEAPEST_TOTAL
    )
    if strat == OptimizationStrategy.CHEAPEST_TOTAL:
        header = t("quote_header_cheapest", lang=lang)
    elif strat == OptimizationStrategy.SINGLE_SHOP:
        header = t("quote_header_single_shop", lang=lang)
    elif strat == OptimizationStrategy.FASTEST:
        header = t("quote_header_fastest", lang=lang)
    elif strat == OptimizationStrategy.PREMIUM:
        header = t("quote_header_premium", lang=lang)
    else:
        header = t("quote_header_balanced", lang=lang)

    shop_sections = []
    for g in variant.shop_groups:
        lines_str = "\n".join(
            f"   • {esc(line.product_name)} × {format_qty(line.billed_qty)} {esc(line.pack_unit)} "
            f"....... {line.line_cost_uzs:,.0f}"
            for line in g.lines
        )
        fee_str = "bepul" if g.is_free_delivery else f"{g.delivery_fee_uzs:,.0f}"
        dist_str = f" — {g.distance_km:.1f} km" if g.distance_km else ""
        shop_sections.append(
            f"🏪 <b>{g.shop_name}</b>{dist_str}\n"
            f"{lines_str}\n"
            f"   <i>Jami: {g.subtotal_uzs:,.0f} + dostavka {fee_str}</i>"
        )

    divider = "──────────────────────────────"
    savings_str = (
        t(
            "quote_savings",
            lang=lang,
            amount=f"{variant.savings_vs_worst_uzs:,.0f}",
            pct=f"{variant.savings_pct:.1f}",
        )
        if variant.savings_vs_worst_uzs > Decimal("0")
        else ""
    )
    coverage_str = t(
        "quote_coverage", lang=lang, covered=variant.covered_count, total=variant.total_count
    )
    eta_str = t(
        "quote_delivery_eta",
        lang=lang,
        eta_min=settings.delivery_eta_min_hours,
        eta_max=settings.delivery_eta_max_hours,
    )

    summary = (
        f"{divider}\n"
        f"{t('quote_items_total', lang=lang)}      {variant.items_total_uzs:,.0f} so'm\n"
        f"{t('quote_delivery_total', lang=lang)}   {variant.delivery_total_uzs:,.0f} so'm\n"
        f"<b>{t('quote_grand_total', lang=lang)}   {variant.grand_total_uzs:,.0f} so'm</b>\n"
        f"{savings_str}\n"
        f"{coverage_str}\n"
        f"{eta_str}"
    )

    return f"{header}\n\n" + "\n\n".join(shop_sections) + f"\n\n{summary}"


def _serialize_variant(v: QuoteVariant) -> dict[str, Any]:
    groups = []
    for g in v.shop_groups:
        lines = []
        for line in g.lines:
            lines.append(
                {
                    "line_no": line.line_no,
                    "canonical_id": line.canonical_id,
                    "product_name": line.product_name,
                    "shop_id": line.shop_id,
                    "shop_name": line.shop_name,
                    "offer_id": line.offer_id,
                    "needed_qty": str(line.needed_qty),
                    "needed_unit": line.needed_unit,
                    "pack_size": str(line.pack_size),
                    "pack_unit": line.pack_unit,
                    "packs_needed": line.packs_needed,
                    "billed_qty": str(line.billed_qty),
                    "overage_qty": str(line.overage_qty),
                    "unit_price_uzs": str(line.unit_price_uzs),
                    "line_cost_uzs": str(line.line_cost_uzs),
                }
            )
        groups.append(
            {
                "shop_id": g.shop_id,
                "shop_name": g.shop_name,
                "district_name": g.district_name,
                "distance_km": g.distance_km,
                "lines": lines,
                "subtotal_uzs": str(g.subtotal_uzs),
                "delivery_fee_uzs": str(g.delivery_fee_uzs),
                "is_free_delivery": g.is_free_delivery,
                "eta_hours": g.eta_hours,
                "trust_score": g.trust_score,
            }
        )

    return {
        "strategy_labels": [s.value for s in v.strategy_labels],
        "shop_groups": groups,
        "items_total_uzs": str(v.items_total_uzs),
        "delivery_total_uzs": str(v.delivery_total_uzs),
        "grand_total_uzs": str(v.grand_total_uzs),
        "coverage_pct": v.coverage_pct,
        "covered_count": v.covered_count,
        "total_count": v.total_count,
        "savings_vs_worst_uzs": str(v.savings_vs_worst_uzs),
        "savings_pct": v.savings_pct,
        "max_eta_hours": v.max_eta_hours,
    }


def _deserialize_variant(d: dict[str, Any]) -> QuoteVariant:
    from app.domain.optimizer.models import LineAssignment, ShopQuoteGroup

    groups = []
    for g in d["shop_groups"]:
        lines = []
        for line in g["lines"]:
            lines.append(
                LineAssignment(
                    line_no=line["line_no"],
                    canonical_id=line["canonical_id"],
                    product_name=line["product_name"],
                    shop_id=line["shop_id"],
                    shop_name=line["shop_name"],
                    offer_id=line["offer_id"],
                    needed_qty=Decimal(line["needed_qty"]),
                    needed_unit=line["needed_unit"],
                    pack_size=Decimal(line["pack_size"]),
                    pack_unit=line["pack_unit"],
                    packs_needed=line["packs_needed"],
                    billed_qty=Decimal(line["billed_qty"]),
                    overage_qty=Decimal(line["overage_qty"]),
                    unit_price_uzs=Decimal(line["unit_price_uzs"]),
                    line_cost_uzs=Decimal(line["line_cost_uzs"]),
                )
            )
        groups.append(
            ShopQuoteGroup(
                shop_id=g["shop_id"],
                shop_name=g["shop_name"],
                district_name=g["district_name"],
                distance_km=g["distance_km"],
                lines=tuple(lines),
                subtotal_uzs=Decimal(g["subtotal_uzs"]),
                delivery_fee_uzs=Decimal(g["delivery_fee_uzs"]),
                is_free_delivery=g["is_free_delivery"],
                eta_hours=g["eta_hours"],
                trust_score=g["trust_score"],
            )
        )

    return QuoteVariant(
        strategy_labels=tuple(OptimizationStrategy(s) for s in d["strategy_labels"]),
        shop_groups=tuple(groups),
        items_total_uzs=Decimal(d["items_total_uzs"]),
        delivery_total_uzs=Decimal(d["delivery_total_uzs"]),
        grand_total_uzs=Decimal(d["grand_total_uzs"]),
        coverage_pct=d["coverage_pct"],
        covered_count=d["covered_count"],
        total_count=d["total_count"],
        missing_lines=(),
        savings_vs_worst_uzs=Decimal(d["savings_vs_worst_uzs"]),
        savings_pct=d["savings_pct"],
        max_eta_hours=d["max_eta_hours"],
    )
