"""Telegram adapter for the same durable conversation used by the storefront."""

from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.customer import _format_quote_card, _not_a_menu_button
from app.bot.keyboards.inline import get_order_confirm_keyboard
from app.bot.states import BasketStates
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.models.conversation import Conversation, ConversationJob, ConversationMessage
from app.db.models.user import User
from app.domain.optimizer.serde import deserialize_variant
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.services.chat_progress import resume_markup
from app.services.conversation_service import ConversationService
from app.services.sales_agent import AgentCart, agent_available

router = Router(name="ai_chat")
router.callback_query.filter(F.message.chat.type == "private")


def product_keyboard(
    message: ConversationMessage, revision: int, lang: str
) -> InlineKeyboardMarkup:
    rows = []
    for index, card in enumerate(message.cards[:3]):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{index + 1}. {card['name']}",
                    callback_data=f"chat:product:{message.id}:{index}:{revision}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=t("sales_view_cart", lang=lang), callback_data="g:cart")]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("web_chat_operator", lang=lang), callback_data="chat:operator"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quantity_keyboard(
    message: ConversationMessage, index: int, revision: int, lang: str
) -> InlineKeyboardMarkup:
    card = message.cards[index]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{qty} {card.get('unit_code', '')}",
                    callback_data=f"chat:qty:{message.id}:{index}:{qty}:{revision}",
                )
                for qty in (1, 5, 10)
            ],
            [
                InlineKeyboardButton(
                    text=t("sales_custom_qty", lang=lang),
                    callback_data=f"chat:custom:{message.id}:{index}:{revision}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("sales_back_variants", lang=lang),
                    callback_data=f"chat:variants:{message.id}",
                )
            ],
            [InlineKeyboardButton(text=t("sales_view_cart", lang=lang), callback_data="g:cart")],
            [
                InlineKeyboardButton(
                    text=t("web_chat_operator", lang=lang), callback_data="chat:operator"
                )
            ],
        ]
    )


@router.callback_query(F.data.startswith("chat:product:"))
async def select_product(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    parts = (callback.data or "").split(":")
    try:
        if len(parts) != 5 or not all(value.isdigit() for value in parts[2:]):
            raise InvalidCartItem("invalid_callback")
        message_id, index, revision = map(int, parts[2:])
        message = await session.get(ConversationMessage, message_id)
        conversation = await session.get(Conversation, message.conversation_id) if message else None
        if message is None or conversation is None or conversation.user_id != user.id:
            raise InvalidCartItem("invalid_message")
        if not 0 <= index < min(3, len(message.cards)):
            raise InvalidCartItem("invalid_card")
        card = message.cards[index]
    except (InvalidCartItem, KeyError, ValueError):
        await callback.answer(t("web_chat_cart_conflict", lang=lang), show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        price = (
            f"{card['price_from_uzs']} UZS / {card.get('unit', '')}"
            if card.get("price_from_uzs") is not None
            else t("sales_price_request", lang=lang)
        )
        await callback.message.answer(
            f"{index + 1}. {card['name']}\n"
            f"{price}\n\n"
            f"{t('chat_choose_quantity', lang=lang)}",
            parse_mode=None,
            reply_markup=quantity_keyboard(message, index, revision, lang),
        )


def _agent_is_available(_event: Message, **_data: Any) -> bool:
    """Retained for callers; human conversations must route even when AI is off."""
    return agent_available()


async def _durable_chat_enabled(_event: Message, user: User, session: AsyncSession) -> bool:
    if agent_available():
        return True
    status = await session.scalar(
        select(Conversation.status).where(Conversation.user_id == user.id)
    )
    return status in {"waiting", "human"}


@router.message(
    StateFilter(None, BasketStates.waiting_for_basket_text, BasketStates.viewing_quotes),
    F.chat.type == "private",
    F.text & ~F.text.startswith("/"),
    _not_a_menu_button,
    _durable_chat_enabled,
)
async def handle_ai_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
) -> None:
    await CartService(session).migrate_legacy(user.id, await state.get_data())
    job = await ConversationService(session).submit(
        user,
        message.text or "",
        f"tg:{message.chat.id}:{message.message_id}",
        "telegram",
    )
    await session.commit()
    from app.services.chat_progress import acknowledge

    await acknowledge(message, session, job["id"], lang)


@router.callback_query(F.data.startswith("chat:checkout:"))
async def prepare_confirmation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str,
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    job = await session.get(ConversationJob, int(raw_id)) if raw_id.isdigit() else None
    conversation = await session.get(Conversation, job.conversation_id) if job else None
    if conversation is None or conversation.user_id != user.id or conversation.status != "ai":
        await callback.answer(t("error_generic", lang=lang), show_alert=True)
        return
    cart = AgentCart.from_dict(conversation.agent_state)
    snapshot = await CartService(session).get(user.id)
    if not cart.order or not cart.quote or cart.quote_revision != snapshot.revision:
        await callback.answer(t("quote_not_orderable", lang=lang), show_alert=True)
        return
    variant = deserialize_variant(cart.quote)
    raw_district = cart.order.get("district_id")
    await state.update_data(
        quotes=[cart.quote],
        selected_quote_idx=0,
        contact_phone=cart.order["phone"],
        delivery_address=cart.order["address"],
        order_comment=cart.order["comment"],
        # The confirm handler re-prices the basket, and it must do so for the
        # district the agent agreed with the customer rather than the one on
        # their profile -- a site is often not where they live.
        delivery_district_id=int(raw_district) if raw_district else user.district_id,
        cart_revision=snapshot.revision,
        quote_cart_revision=snapshot.revision,
        checkout_key=f"chat:{job.id}" if job else None,
    )
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"{_format_quote_card(variant, lang=lang)}\n\n{t('order_confirm_question', lang=lang)}",
            reply_markup=get_order_confirm_keyboard(lang=lang),
        )


def resume_keyboard(lang: str) -> InlineKeyboardMarkup:
    """The way back from an unclaimed handoff.

    Defined once in `chat_progress`, which the worker also uses when it
    acknowledges a message that went to the operator queue -- the customer must
    see the same offer whether they just asked for an operator or asked
    yesterday and is still waiting.
    """
    return resume_markup(lang)


@router.callback_query(F.data == "chat:operator")
async def handoff_callback(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    await ConversationService(session).handoff(user, channel="telegram")
    await session.commit()
    await callback.answer(t("chat_waiting", lang=lang))
    if isinstance(callback.message, Message):
        await callback.message.answer(
            t("chat_waiting", lang=lang) + "\n" + t("web_chat_waiting_hint", lang=lang),
            parse_mode=None,
            reply_markup=resume_keyboard(lang),
        )


@router.callback_query(F.data == "chat:resume_ai")
async def resume_ai_callback(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    result = await ConversationService(session).resume_ai(user, channel="telegram")
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            t("web_chat_ai_resumed", lang=lang)
            if result["status"] == "ai"
            else t("web_chat_assigned", lang=lang),
            parse_mode=None,
        )


@router.callback_query(F.data.startswith("chat:qty:"))
async def set_product_quantity(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    parts = (callback.data or "").split(":")
    try:
        if len(parts) != 6 or not all(value.isdigit() for value in parts[2:]):
            raise InvalidCartItem("invalid_callback")
        message_id, index, qty, revision = map(int, parts[2:])
        message = await session.get(ConversationMessage, message_id)
        conversation = await session.get(Conversation, message.conversation_id) if message else None
        if conversation is None or conversation.user_id != user.id or message is None:
            raise InvalidCartItem("invalid_message")
        if not 0 <= index < len(message.cards) or qty not in {1, 5, 10}:
            raise InvalidCartItem("invalid_card")
        card = message.cards[index]
        product = await session.get(CanonicalProduct, card["id"])
        if product is None:
            raise InvalidCartItem("invalid_product")
        await CartService(session)._check(user.id, revision)
        if isinstance(callback.message, Message):
            from app.bot.handlers.guided_sales import preview_quantity

            await preview_quantity(callback.message, session, product.id, str(qty), revision, lang)
    except (CartConflict, InvalidCartItem, KeyError, ValueError):
        await session.rollback()
        await callback.answer(t("web_chat_cart_conflict", lang=lang), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("chat:custom:"))
async def custom_product_quantity(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, lang: str
) -> None:
    from app.bot.handlers.guided_sales import GuidedStates, keyboard

    try:
        _, _, raw_id, raw_index, raw_revision = (callback.data or "").split(":")
        message = await session.get(ConversationMessage, int(raw_id))
        conversation = await session.get(Conversation, message.conversation_id) if message else None
        if (
            not message
            or not conversation
            or conversation.user_id != user.id
            or not 0 <= int(raw_index) < min(3, len(message.cards))
        ):
            raise ValueError("invalid_card")
        card = message.cards[int(raw_index)]
        product = await session.get(CanonicalProduct, card["id"])
        if not product:
            raise ValueError("invalid_product")
        await CartService(session)._check(user.id, int(raw_revision))
        await state.update_data(guided_product=product.id, guided_revision=int(raw_revision))
        await state.set_state(GuidedStates.quantity)
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                t("sales_enter_qty", lang=lang, unit=product.base_unit_code),
                reply_markup=keyboard(
                    (t("sales_back_variants", lang=lang), f"chat:variants:{message.id}"),
                    (t("sales_view_cart", lang=lang), "g:cart"),
                ),
            )
    except (ValueError, KeyError, CartConflict):
        await callback.answer(t("web_chat_cart_conflict", lang=lang), show_alert=True)


@router.callback_query(F.data.startswith("chat:variants:"))
async def back_variants(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, lang: str
) -> None:
    raw = (callback.data or "").split(":")[-1]
    message = await session.get(ConversationMessage, int(raw)) if raw.isdigit() else None
    conversation = await session.get(Conversation, message.conversation_id) if message else None
    if (
        message
        and conversation
        and conversation.user_id == user.id
        and isinstance(callback.message, Message)
    ):
        await state.set_state(None)
        cart = await CartService(session).get(user.id)
        await callback.message.answer(
            t("sales_choose_product", lang=lang),
            reply_markup=product_keyboard(message, cart.revision, lang),
        )
    await callback.answer()
