"""Deterministic quantity, cart navigation and manual enquiry wizard (no AI calls)."""

from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import localized_name
from app.bot.keyboards.inline import region_label
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.models.sales_request import SalesRequest
from app.db.models.shop import District
from app.db.models.user import User
from app.db.repositories.shop_repo import ShopRepository
from app.domain.normalize.phone import normalize_uz_phone
from app.services.cart_policy import assess_lines
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.services.sales_request_service import SalesRequestService, contact_defaults

router = Router(name="guided_sales")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class GuidedStates(StatesGroup):
    quantity = State()
    contact = State()
    district = State()
    confirmation = State()


def keyboard(*rows: tuple[str, str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label[:64], callback_data=data)] for label, data in rows
        ]
    )


def next_keyboard(
    lang: str, product_id: int | None = None, revision: int = 0
) -> InlineKeyboardMarkup:
    rows = [
        (t("sales_view_cart", lang=lang), "g:cart"),
        (t("sales_more_products", lang=lang), "g:more"),
        (t("sales_back_variants", lang=lang), "g:variants"),
        (t("sales_back_chat", lang=lang), "g:back"),
    ]
    if product_id:
        rows.insert(2, (t("sales_edit_qty", lang=lang), f"g:edit:{product_id}:{revision}"))
    return keyboard(*rows)


async def preview_quantity(
    message: Message, session: AsyncSession, product_id: int, qty: str, revision: int, lang: str
) -> None:
    product = await session.get(CanonicalProduct, product_id)
    if product is None:
        raise InvalidCartItem("invalid_product")
    amount, unit = await CartService(session)._validate(product.id, qty, product.base_unit_code)
    amount_text = format(amount.normalize(), "f")
    name = localized_name(product.name_uz, product.name_ru, lang, name_uz_cyrl=product.name_uz_cyrl)
    await message.answer(
        f"{name}\n{amount_text} {unit}",
        parse_mode=None,
        reply_markup=keyboard(
            (t("web_chat_add", lang=lang), f"g:add:{product.id}:{amount_text}:{revision}"),
            (t("sales_back", lang=lang), "g:cart"),
        ),
    )


async def show_cart(message: Message, session: AsyncSession, user: User, lang: str) -> None:
    cart = await CartService(session).get(user.id)
    lines = await assess_lines(session, cart.lines)
    await session.commit()
    text = t("sales_cart", lang=lang) + "\n\n"
    buttons = []
    for line in lines:
        label = (
            t("sales_price_request", lang=lang)
            if line["requires_confirmation"]
            else f"{line['reference_unit_price']} UZS / {line['price_unit_code']}"
        )
        text += f"{line['canonical_name']} — {line['qty']} {line['unit_code']}\n{label}\n\n"
        buttons.extend(
            [
                (
                    t("sales_edit_qty", lang=lang) + f" · {line['canonical_name']}",
                    f"g:edit:{line['canonical_id']}:{cart.revision}",
                ),
                (
                    t("sales_remove", lang=lang) + f" · {line['canonical_name']}",
                    f"g:remove:{line['canonical_id']}:{cart.revision}",
                ),
            ]
        )
    if lines:
        manual = any(line["requires_confirmation"] for line in lines)
        if manual:
            text += t("sales_request_hint", lang=lang)
        buttons.append(
            (
                t("sales_send_request" if manual else "sales_calculate", lang=lang),
                "g:request" if manual else "g:checkout",
            )
        )
    else:
        text += t("sales_empty_cart", lang=lang)
    buttons.extend(
        [
            (t("sales_more_products", lang=lang), "g:more"),
            (t("sales_requests", lang=lang), "g:requests"),
            (t("sales_back_chat", lang=lang), "g:back"),
        ]
    )
    # Keep each Telegram keyboard bounded even for a 60-line basket.
    for start in range(0, len(text), 3500):
        await message.answer(
            text[start : start + 3500],
            parse_mode=None,
            reply_markup=keyboard(*buttons[:30]) if start + 3500 >= len(text) else None,
        )
    for start in range(30, len(buttons), 30):
        await message.answer(
            t("sales_cart", lang=lang), reply_markup=keyboard(*buttons[start : start + 30])
        )


@router.callback_query(F.data.startswith("g:add:"))
async def add_quantity(
    callback: CallbackQuery, session: AsyncSession, user: User, state: FSMContext, lang: str
) -> None:
    try:
        _, _, raw_id, qty, raw_revision = (callback.data or "").split(":")
        snapshot = await CartService(session).set_item(
            user.id, int(raw_id), qty, expected_revision=int(raw_revision)
        )
        product = await session.get(CanonicalProduct, int(raw_id))
        assert product is not None
        name = localized_name(
            product.name_uz, product.name_ru, lang, name_uz_cyrl=product.name_uz_cyrl
        )
        unit = product.base_unit_code
        await session.commit()
        await state.set_state(None)
        await state.update_data(
            basket_lines=[], quotes=[], cart_revision=snapshot.revision, cart_user_id=user.id
        )
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=next_keyboard(lang, product.id, snapshot.revision)
            )
            await callback.message.answer(
                t("sales_in_cart", lang=lang, name=name, qty=qty, unit=unit),
                parse_mode=None,
                reply_markup=next_keyboard(lang, product.id, snapshot.revision),
            )
    except (ValueError, InvalidCartItem, CartConflict):
        await session.rollback()
        await session.refresh(user)
        await callback.answer(t("web_chat_cart_conflict", lang=lang), show_alert=True)
        if isinstance(callback.message, Message):
            await show_cart(callback.message, session, user, lang)


@router.callback_query(F.data.startswith("g:edit:"))
async def edit_quantity(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, lang: str
) -> None:
    try:
        _, _, raw_id, raw_revision = (callback.data or "").split(":")
        product_id, revision = int(raw_id), int(raw_revision)
        cart = await CartService(session).get(user.id)
        if cart.revision != revision or not any(
            i["canonical_id"] == product_id for i in cart.lines
        ):
            raise ValueError("stale")
        product = await session.get(CanonicalProduct, product_id)
        assert product is not None
        await state.update_data(guided_product=product.id, guided_revision=revision)
        await state.set_state(GuidedStates.quantity)
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                t("sales_enter_qty", lang=lang, unit=product.base_unit_code),
                reply_markup=keyboard((t("sales_back", lang=lang), "g:cart")),
            )
    except (ValueError, AssertionError):
        await callback.answer(t("web_chat_cart_conflict", lang=lang), show_alert=True)


@router.message(GuidedStates.quantity, F.text)
async def custom_quantity(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    data = await state.get_data()
    try:
        await preview_quantity(
            message,
            session,
            int(data["guided_product"]),
            (message.text or "").strip().replace(",", "."),
            int(data["guided_revision"]),
            lang,
        )
    except (ValueError, KeyError, InvalidCartItem, ArithmeticError):
        await message.answer(
            t("qty_out_of_range", lang=lang),
            reply_markup=keyboard((t("sales_back", lang=lang), "g:cart")),
        )


async def ask_contact(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    data = await state.get_data()
    contact = data.get("guided_contact", {})
    for field in ("name", "phone", "district_id", "address"):
        if contact.get(field):
            continue
        await state.update_data(guided_field=field)
        if field == "district_id":
            await state.set_state(GuidedStates.district)
            await region_page(message, session, lang)
        else:
            await state.set_state(GuidedStates.contact)
            await message.answer(
                t("sales_contact_prompt", lang=lang, field=t("sales_" + field, lang=lang)),
                reply_markup=keyboard((t("sales_back", lang=lang), "g:cart")),
            )
        return
    await state.set_state(GuidedStates.confirmation)
    district = await session.get(District, contact["district_id"])
    district_name = localized_name(district.name_uz, district.name_ru, lang) if district else ""
    await message.answer(
        f"{contact['name']}\n{contact['phone']}\n{district_name}, {contact['address']}\n\n"
        + t("sales_request_hint", lang=lang),
        parse_mode=None,
        reply_markup=keyboard(
            (t("sales_send_request", lang=lang), f"g:send:{data['guided_key']}"),
            (t("sales_contact_edit", lang=lang), "g:contactedit"),
            (t("sales_back", lang=lang), "g:cart"),
        ),
    )


async def region_page(message: Message, session: AsyncSession, lang: str) -> None:
    """Ask for the region first: the country has 200 districts, not fifteen."""
    regions = await ShopRepository(session).list_regions()
    buttons = [(region_label(r, lang), f"g:region:{r}") for r in regions]
    buttons.append((t("sales_back", lang=lang), "g:cart"))
    await message.answer(t("choose_region", lang=lang), reply_markup=keyboard(*buttons))


async def district_page(
    message: Message, session: AsyncSession, region: str, page: int, lang: str
) -> None:
    rows = (
        await session.scalars(
            select(District)
            .where(District.region == region)
            .order_by(District.name_uz)
            .offset(page * 15)
            .limit(16)
        )
    ).all()
    buttons = [
        (localized_name(r.name_uz, r.name_ru, lang), f"g:district:{r.id}") for r in rows[:15]
    ]
    if page:
        buttons.append(("←", f"g:districtpage:{page - 1}:{region}"))
    if len(rows) > 15:
        buttons.append(("→", f"g:districtpage:{page + 1}:{region}"))
    buttons.append((t("sales_back", lang=lang), "g:regions"))
    await message.answer(t("sales_district", lang=lang), reply_markup=keyboard(*buttons))


async def start_request(
    message: Message, state: FSMContext, session: AsyncSession, user: User, lang: str
) -> None:
    snapshot = await CartService(session).get(user.id)
    if not snapshot.lines:
        await show_cart(message, session, user, lang)
        return
    await state.update_data(
        guided_revision=snapshot.revision,
        guided_key=uuid4().hex,
        guided_contact=await contact_defaults(session, user),
    )
    await session.commit()
    await ask_contact(message, state, session, lang)


@router.message(GuidedStates.contact, F.text | F.contact)
async def contact_input(
    message: Message, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    data = await state.get_data()
    field = data.get("guided_field")
    value = (message.contact.phone_number if message.contact else message.text or "").strip()
    if field == "phone":
        value = normalize_uz_phone(value) or ""
    if (
        not value
        or field not in {"name", "phone", "address"}
        or len(value) > (100 if field == "name" else 32 if field == "phone" else 500)
        or (field == "address" and len(value) < 5)
    ):
        await message.answer(t("web_error_generic", lang=lang))
        await ask_contact(message, state, session, lang)
        return
    contact = data["guided_contact"]
    contact[field] = value
    await state.update_data(guided_contact=contact)
    await ask_contact(message, state, session, lang)


@router.callback_query(F.data.startswith("g:"))
async def navigate(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, lang: str
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    action = (callback.data or "")[2:]
    await callback.answer()
    if action in {"cart", "back", "more"}:
        await state.set_state(None)
        if action == "cart":
            await show_cart(callback.message, session, user, lang)
        else:
            await callback.message.answer(
                t("sales_search_prompt", lang=lang), reply_markup=next_keyboard(lang)
            )
    elif action in {"request", "checkout"}:
        cart = await CartService(session).get(user.id)
        lines = await assess_lines(session, cart.lines)
        if action == "checkout" and lines and not any(i["requires_confirmation"] for i in lines):
            from app.web.storefront.quoting import optimize, validate_lines

            basket = await validate_lines(session, list(cart.lines))
            variants = await optimize(session, basket.items, district_id=user.district_id)
            if any(not v.missing_lines for v in variants):
                from app.bot.handlers.customer import callback_calculate_quotes

                await state.update_data(
                    basket_lines=list(cart.lines), cart_user_id=user.id, cart_revision=cart.revision
                )
                await callback_calculate_quotes(callback, state, session, user, lang)
                return
        await start_request(callback.message, state, session, user, lang)
    elif action == "contactedit":
        if (await state.get_data()).get("guided_key"):
            await state.update_data(guided_contact={})
            await ask_contact(callback.message, state, session, lang)
    elif action == "regions" and await state.get_state() == GuidedStates.district.state:
        await region_page(callback.message, session, lang)
    elif action.startswith("region:") and await state.get_state() == GuidedStates.district.state:
        await district_page(callback.message, session, action.split(":", 1)[1], 0, lang)
    elif (
        action.startswith("districtpage:")
        and await state.get_state() == GuidedStates.district.state
    ):
        _, page, region = action.split(":", 2)
        if page.isdigit() and int(page) <= 100:
            await district_page(callback.message, session, region, int(page), lang)
    elif action.startswith("district:") and await state.get_state() == GuidedStates.district.state:
        raw = action.split(":")[1]
        if raw.isdigit() and (await session.get(District, int(raw))) is not None:
            data = await state.get_data()
            data["guided_contact"]["district_id"] = int(raw)
            await state.update_data(guided_contact=data["guided_contact"])
            await ask_contact(callback.message, state, session, lang)
    elif action.startswith("send:"):
        key = action.split(":")[1]
        data = await state.get_data()
        row = await session.scalar(
            select(SalesRequest).where(
                SalesRequest.user_id == user.id, SalesRequest.idempotency_key == "tg:" + key
            )
        )
        try:
            if row is None:
                if (
                    key != data.get("guided_key")
                    or await state.get_state() != GuidedStates.confirmation.state
                ):
                    raise ValueError("stale")
                contact = data["guided_contact"]
                row = await SalesRequestService(session).create(
                    user,
                    revision=data["guided_revision"],
                    key="tg:" + key,
                    name=contact["name"],
                    phone=contact["phone"],
                    district_id=contact["district_id"],
                    address=contact["address"],
                    channel="telegram",
                )
                await session.commit()
                await state.clear()
            await callback.message.answer(
                t("sales_request_sent", lang=lang, id=row.id),
                reply_markup=keyboard(
                    (t("sales_requests", lang=lang), "g:requests"),
                    (t("sales_back_chat", lang=lang), "g:back"),
                    (t("sales_more_products", lang=lang), "g:more"),
                ),
            )
        except (InvalidCartItem, CartConflict, ValueError, KeyError):
            await session.rollback()
            await callback.message.answer(
                t("web_chat_cart_conflict", lang=lang), reply_markup=next_keyboard(lang)
            )
    elif action.startswith("remove:"):
        try:
            _, raw_id, revision = action.split(":")
            await CartService(session).remove_item(
                user.id, int(raw_id), expected_revision=int(revision)
            )
            await session.commit()
        except (ValueError, CartConflict, InvalidCartItem):
            await session.rollback()
            await session.refresh(user)
            await callback.message.answer(t("web_chat_cart_conflict", lang=lang))
        await show_cart(callback.message, session, user, lang)
    elif action == "variants":
        from app.bot.handlers.ai_chat import product_keyboard
        from app.db.models.conversation import Conversation, ConversationMessage

        messages = (
            await session.scalars(
                select(ConversationMessage)
                .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
                .where(Conversation.user_id == user.id, ConversationMessage.role == "assistant")
                .order_by(ConversationMessage.id.desc())
                .limit(20)
            )
        ).all()
        last = next((item for item in messages if item.cards), None)
        await state.set_state(None)
        cart = await CartService(session).get(user.id)
        await callback.message.answer(
            t("sales_choose_product", lang=lang),
            reply_markup=product_keyboard(last, cart.revision, lang)
            if last
            else next_keyboard(lang),
        )
    elif action == "requests":
        rows = (
            await session.scalars(
                select(SalesRequest)
                .where(SalesRequest.user_id == user.id)
                .order_by(SalesRequest.id.desc())
                .limit(20)
            )
        ).all()
        if not rows:
            await callback.message.answer(
                t("sales_empty", lang=lang), reply_markup=next_keyboard(lang)
            )
        for row in rows:
            body = f"#{row.id} · {t('sales_request_' + row.status, lang=lang)}\n" + "\n".join(
                f"{i.name} — {i.qty:g} {i.unit_code}" for i in row.items
            )
            if row.resolution_note:
                body += "\n" + row.resolution_note
            for pos in range(0, len(body), 3500):
                await callback.message.answer(
                    body[pos : pos + 3500],
                    parse_mode=None,
                    reply_markup=next_keyboard(lang) if pos + 3500 >= len(body) else None,
                )
