import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger("bot.event")


class LoggingMiddleware(BaseMiddleware):
    """Logging middleware attaching a correlation ID to every incoming Telegram event."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        correlation_id = str(uuid.uuid4())[:8]
        data["correlation_id"] = correlation_id

        logger.debug("Handling Telegram event [%s]: %s", correlation_id, type(event).__name__)
        result = await handler(event, data)
        logger.debug("Completed Telegram event [%s]", correlation_id)
        return result
