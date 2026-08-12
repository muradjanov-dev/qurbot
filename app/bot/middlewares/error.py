import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.i18n import t

logger = logging.getLogger(__name__)


class ErrorMiddleware(BaseMiddleware):
    """Global error middleware: logs unexpected errors and sends localized friendly notification."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            corr_id = data.get("correlation_id", "unknown")
            logger.exception(
                "Unhandled error processing event [correlation_id=%s]: %s", corr_id, exc
            )

            lang = data.get("lang", "uz_latn")
            msg_text = t("error_generic", lang=lang)

            if isinstance(event, Message):
                await event.answer(msg_text)
            elif isinstance(event, CallbackQuery) and event.message:
                await event.answer(msg_text, show_alert=True)
            return None
