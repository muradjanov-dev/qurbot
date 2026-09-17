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
from app.services.conversation_service import ConversationService
from app.services.sales_agent import AgentCart, agent_available

router = Router(name="ai_chat")
router.callback_query.filter(F.message.chat.type == "private")


def product_keyboard(
    message: ConversationMessage, revision: int, lang: str
) -> InlineKeyboardMarkup:
    rows = []
    for index, card in enumerate(message.cards[:3]):
        if (
            card.get("price_from_uzs") is None
            or card.get("price_on_request")
            or card.get("stock_unverified")
        ):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{card['name'][:25]} · {t('web_qty', lang=lang)} "
                        f"{qty} {card.get('unit_code', '')}"
                    ),
                    callback_data=f"chat:qty:{message.id}:{index}:{qty}:{revision}",
                )
                for qty in (1, 5, 10)
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("web_chat_operator", lang=lang), callback_data="chat:operator"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    await message.answer(
        t("chat_waiting" if job["status"] == "human" else "chat_queued", lang=lang)
    )


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
    await state.update_data(
        quotes=[cart.quote],
        selected_quote_idx=0,
        contact_phone=cart.order["phone"],
        delivery_address=cart.order["address"],
        order_comment=cart.order["comment"],
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


@router.callback_query(F.data == "chat:operator")
async def handoff_callback(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    await ConversationService(session).handoff(user)
    await session.commit()
    await callback.answer(t("chat_waiting", lang=lang))


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
        if (
            product is None
            or product.attributes.get("price_on_request")
            or product.attributes.get("stock_unverified")
            or card.get("price_from_uzs") is None
        ):
            raise InvalidCartItem("unverified_product")
        snapshot = await CartService(session).set_item(
            user.id,
            product.id,
            qty,
            expected_revision=revision,
            unit_code=product.base_unit_code,
        )
        await session.commit()
    except (CartConflict, InvalidCartItem, KeyError, ValueError):
        await session.rollback()
        await callback.answer(t("web_chat_cart_conflict", lang=lang), show_alert=True)
        return
    await callback.answer(t("web_chat_added", lang=lang))
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=product_keyboard(message, snapshot.revision, lang)
        )
