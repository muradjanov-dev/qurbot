"""Private-chat approval for browser-bound Telegram login challenges."""

from __future__ import annotations

import html
import re
from contextlib import suppress
from urllib.parse import urlsplit

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.types import (
    User as TelegramUser,
)

from app.core.config import settings
from app.core.i18n import DEFAULT_LANG, t
from app.db.models.user import User
from app.services.bot_login import BotLoginUnavailable, State, open_bot_login_service

router = Router(name="bot_login")
_LOGIN_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32}$")
_CALLBACK_DATA = re.compile(r"^web_login:(approve|deny):([A-Za-z0-9_-]{32})$")


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("login_")))
async def start_browser_login(
    message: Message,
    command: CommandObject,
    user: User,
    lang: str,
) -> None:
    telegram_user = message.from_user
    token = _login_token(command.args)
    if (
        telegram_user is None
        or not _is_private_sender(message.chat.type, message.chat.id, telegram_user, user)
        or token is None
    ):
        await message.answer(t("bot_login_invalid", lang=lang or DEFAULT_LANG))
        return

    try:
        async with open_bot_login_service() as service:
            state = await service.claim(token, telegram_user.id)
    except BotLoginUnavailable:
        await message.answer(t("bot_login_unavailable", lang=lang or DEFAULT_LANG))
        return

    if state is None:
        await message.answer(t("bot_login_invalid", lang=lang or DEFAULT_LANG))
        return
    if state.status == "approved":
        await message.answer(t("bot_login_bot_approved", lang=lang or DEFAULT_LANG))
        return
    if state.status == "denied":
        await message.answer(t("bot_login_bot_denied", lang=lang or DEFAULT_LANG))
        return
    if state.status != "claimed":
        await message.answer(t("bot_login_invalid", lang=lang or DEFAULT_LANG))
        return

    await message.answer(
        _approval_prompt(state, lang),
        reply_markup=_approval_keyboard(token, lang),
    )


@router.callback_query(F.data.startswith("web_login:"))
async def decide_browser_login(
    callback: CallbackQuery,
    user: User,
    lang: str,
) -> None:
    telegram_user = callback.from_user
    message = callback.message
    match = _CALLBACK_DATA.fullmatch(callback.data or "")
    if (
        not isinstance(message, Message)
        or telegram_user is None
        or not _is_private_sender(message.chat.type, message.chat.id, telegram_user, user)
        or match is None
    ):
        await callback.answer(t("bot_login_invalid", lang=lang or DEFAULT_LANG), show_alert=True)
        return

    action, token = match.groups()
    try:
        async with open_bot_login_service() as service:
            decided = await service.decide(token, telegram_user.id, approve=action == "approve")
    except BotLoginUnavailable:
        await callback.answer(
            t("bot_login_unavailable", lang=lang or DEFAULT_LANG), show_alert=True
        )
        return

    if not decided:
        await callback.answer(t("bot_login_invalid", lang=lang or DEFAULT_LANG), show_alert=True)
        return

    key = "bot_login_bot_approved" if action == "approve" else "bot_login_bot_denied"
    await callback.answer()
    with suppress(TelegramBadRequest):
        await message.edit_text(t(key, lang=lang or DEFAULT_LANG))


def _approval_prompt(state: State, lang: str) -> str:
    return t(
        "bot_login_bot_prompt",
        lang=lang or DEFAULT_LANG,
        code=html.escape(state.code, quote=True),
        browser=html.escape(state.browser_label, quote=True),
        site=html.escape(_configured_site_host(), quote=True),
    )


def _approval_keyboard(token: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("bot_login_confirm", lang=lang or DEFAULT_LANG),
                    callback_data=f"web_login:approve:{token}",
                ),
                InlineKeyboardButton(
                    text=t("bot_login_cancel", lang=lang or DEFAULT_LANG),
                    callback_data=f"web_login:deny:{token}",
                ),
            ]
        ]
    )


def _login_token(args: str | None) -> str | None:
    if not args or not args.startswith("login_"):
        return None
    token = args.removeprefix("login_")
    return token if _LOGIN_TOKEN.fullmatch(token) else None


def _is_private_sender(
    chat_type: str,
    chat_id: int,
    telegram_user: TelegramUser | None,
    user: User,
) -> bool:
    return bool(
        chat_type == ChatType.PRIVATE
        and telegram_user is not None
        and chat_id == telegram_user.id
        and not user.is_blocked
        and user.tg_id == telegram_user.id
    )


def _configured_site_host() -> str:
    configured = settings.storefront_webapp_url or settings.webhook_base_url
    parsed = urlsplit(configured)
    if parsed.hostname:
        return parsed.hostname
    parsed = urlsplit(f"//{configured}")
    return parsed.hostname or "Tezqur"
