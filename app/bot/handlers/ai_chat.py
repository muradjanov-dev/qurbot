"""Customer chat answered by the AI sales agent.

Registered before the customer router, so free text goes to the agent first.
When the agent is off or cannot answer, the deterministic basket flow runs as
before. The order is still confirmed with the existing button.
"""

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import esc
from app.bot.handlers.customer import (
    _format_quote_card,
    _not_a_menu_button,
    _process_basket_input,
    _serialize_variant,
)
from app.bot.keyboards.inline import get_order_confirm_keyboard
from app.bot.states import BasketStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.user import User
from app.domain.optimizer.serde import deserialize_variant
from app.services.sales_agent import AgentCart, DbAgentTools, SalesAgent, agent_available

router = Router(name="ai_chat")

_AGENT_DATA_KEY = "agent"


@router.message(
    StateFilter(None, BasketStates.waiting_for_basket_text, BasketStates.viewing_quotes),
    F.text & ~F.text.startswith("/"),
    _not_a_menu_button,
    lambda _: agent_available(),
)
async def handle_ai_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    lang: str,
) -> None:
    text = message.text or ""
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    data = await state.get_data()
    cart = AgentCart.from_dict(data.get(_AGENT_DATA_KEY))
    reply = await SalesAgent(session, DbAgentTools(session, user)).reply(text, lang, cart)
    if reply is None:
        await _process_basket_input(message, state, session, lang, text, existing_lines=None)
        return

    await message.answer(esc(reply[: settings.agent_reply_max_chars]))

    if cart.order and cart.quote:
        # Hand over to the existing confirm button: it reads these keys and
        # places the order exactly as the button flow does.
        variant = deserialize_variant(cart.quote)
        await state.update_data(
            quotes=[_serialize_variant(variant)],
            selected_quote_idx=0,
            contact_phone=cart.order["phone"],
            delivery_address=cart.order["address"],
            order_comment=cart.order["comment"],
        )
        summary = t(
            "order_confirm_prompt",
            lang=lang,
            phone=esc(cart.order["phone"] or ""),
            address=esc(cart.order["address"] or ""),
            comment=esc(cart.order["comment"] or t("comment_none", lang=lang)),
        )
        await message.answer(
            f"{summary}\n{_format_quote_card(variant, lang=lang)}\n\n"
            f"{t('order_confirm_question', lang=lang)}",
            reply_markup=get_order_confirm_keyboard(lang=lang),
        )
        cart.order = None

    await state.update_data({_AGENT_DATA_KEY: cart.to_dict()})
