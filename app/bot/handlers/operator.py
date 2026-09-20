"""Operator commands and callbacks; ownership is enforced again in the service."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import t
from app.db.models.user import User
from app.services.conversation_service import ConversationService
from app.services.house_shop import is_admin

router = Router(name="operator")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def operator_keyboard(conversation_id: int, lang: str = "uz_latn") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("sales_inbox", lang=lang),
                    web_app=WebAppInfo(
                        url=(settings.storefront_webapp_url or settings.webhook_base_url).rstrip(
                            "/"
                        )
                        + f"/operator?conversation={conversation_id}"
                    ),
                ),
            ]
        ]
    )


@router.message(Command("operator"))
async def request_operator(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    if is_admin(user):
        await message.answer(t("sales_inbox", lang=lang), reply_markup=operator_keyboard(0, lang))
        return
    await ConversationService(session).handoff(user, channel="telegram")
    await session.commit()
    await message.answer(t("chat_waiting", lang=lang))


@router.callback_query(F.data.startswith("operator:"))
async def operator_action(
    callback: CallbackQuery, user: User, session: AsyncSession, lang: str
) -> None:
    if not is_admin(user):
        await callback.answer(t("chat_claim_conflict", lang=lang), show_alert=True)
        return
    await callback.answer()
    parts = (callback.data or "").split(":")
    conversation_id = int(parts[-1]) if parts[-1].isdigit() else 0
    if isinstance(callback.message, Message):
        await callback.message.answer(
            t("sales_inbox", lang=lang), reply_markup=operator_keyboard(conversation_id, lang)
        )


@router.message(Command("reply"))
async def reply_to_customer(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    if not is_admin(user):
        await message.answer(t("chat_claim_conflict", lang=lang))
        return
    await message.answer(t("sales_inbox", lang=lang), reply_markup=operator_keyboard(0, lang))
