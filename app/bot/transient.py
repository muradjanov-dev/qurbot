"""Explicit tracking for customer conversation messages; checkout stays separate."""

from typing import Any

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.telegram_cleanup import register_transient_message


async def register_inbound(message: Message, session: AsyncSession) -> None:
    if message.chat.type != "private":
        return
    await register_transient_message(
        session,
        chat_id=message.chat.id,
        message_id=message.message_id,
        message_type="ai_customer_inbound",
        sent_at=message.date,
    )


async def transient_answer(
    message: Message,
    session: AsyncSession,
    text: str,
    *,
    message_type: str = "guided_sales_transient",
    **kwargs: Any,
) -> Message:
    sent = await message.answer(text, **kwargs)
    # Only real delivered ids can be registered. Mock messages and ambiguous
    # network failures must never produce a guessed deletion target.
    if (
        isinstance(sent.message_id, int)
        and not isinstance(sent.message_id, bool)
        and sent.message_id > 0
        and message.chat.type == "private"
    ):
        await register_transient_message(
            session,
            chat_id=message.chat.id,
            message_id=sent.message_id,
            message_type=message_type,
            sent_at=sent.date if isinstance(sent, Message) else None,
        )
    return sent
