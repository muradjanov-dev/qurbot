"""Operator commands and callbacks; ownership is enforced again in the service."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.models.user import User
from app.services.conversation_service import ConversationConflict, ConversationService

router = Router(name="operator")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def operator_keyboard(conversation_id: int, lang: str = "uz_latn") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("chat_claim", lang=lang),
                    callback_data=f"operator:claim:{conversation_id}",
                ),
                InlineKeyboardButton(
                    text=t("chat_close", lang=lang),
                    callback_data=f"operator:close:{conversation_id}",
                ),
            ]
        ]
    )


@router.message(Command("operator"))
async def request_operator(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    await ConversationService(session).handoff(user)
    await session.commit()
    await message.answer(t("chat_waiting", lang=lang))


@router.callback_query(F.data.startswith("operator:"))
async def operator_action(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    parts = (callback.data or "").split(":")
    try:
        if len(parts) != 3 or not parts[2].isdigit():
            raise ValueError("invalid_callback")
        service = ConversationService(session)
        if parts[1] == "claim":
            result = await service.claim(user, int(parts[2]))
        elif parts[1] == "close":
            result = await service.close(user, int(parts[2]))
        else:
            raise ValueError("invalid_callback")
        await session.commit()
    except (PermissionError, ConversationConflict, LookupError, ValueError):
        await session.rollback()
        await callback.answer(t("chat_claim_conflict", lang=lang), show_alert=True)
        return
    await callback.answer(t("chat_claimed" if parts[1] == "claim" else "chat_closed", lang=lang))
    if parts[1] == "claim" and isinstance(callback.message, Message):
        transcript = "\n".join(f"{row['role']}: {row['text']}" for row in result["messages"])
        await callback.message.answer(
            f"#{parts[2]}\n{transcript[-3000:]}\n\n/reply {parts[2]} …",
            parse_mode=None,
        )


@router.message(Command("reply"))
async def reply_to_customer(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    parts = (message.text or "").split(maxsplit=2)
    try:
        if len(parts) != 3 or not parts[1].isdigit():
            raise ValueError("invalid_reply")
        await ConversationService(session).operator_reply(
            user,
            int(parts[1]),
            parts[2],
            f"tg:{message.chat.id}:{message.message_id}",
        )
        await session.commit()
    except (PermissionError, ConversationConflict, LookupError, ValueError):
        await session.rollback()
        await message.answer(t("chat_claim_conflict", lang=lang))
        return
    await message.answer(t("chat_reply_sent", lang=lang))
