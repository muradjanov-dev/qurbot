"""Persists handler-selected Telegram transient message ids."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.telegram_cleanup import register_transient_message


class TelegramCleanupMiddleware(BaseMiddleware):
    """Register only ids explicitly queued by an eligible chat handler."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)
        queued = data.pop("telegram_cleanup_messages", ())
        session = data.get("session")
        if not queued:
            return result
        if not isinstance(session, AsyncSession):
            raise RuntimeError("Telegram cleanup registrations require the DB session middleware")

        for chat_id, message_id, message_type, sent_at in queued:
            await register_transient_message(
                session,
                chat_id=chat_id,
                message_id=message_id,
                message_type=message_type,
                sent_at=sent_at,
            )
        return result
