import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("bot.throttle")


class ThrottleMiddleware(BaseMiddleware):
    """In-memory sliding window rate limiter per user.

    Limits:
    - Default: 20 messages per minute
    - Quote requests: 3 computations per minute
    """

    def __init__(self, limit_per_minute: int = 20) -> None:
        self.limit_per_minute = limit_per_minute
        self.user_timestamps: dict[int, list[float]] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Message | CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        now = time.time()
        window_start = now - 60.0

        # Prune old timestamps
        history = [ts for ts in self.user_timestamps[user_id] if ts > window_start]
        self.user_timestamps[user_id] = history

        if len(history) >= self.limit_per_minute:
            logger.warning(
                "Throttling user %d: exceeded %d requests/min", user_id, self.limit_per_minute
            )
            # Silently drop flood request according to SPEC §9
            return None

        self.user_timestamps[user_id].append(now)
        return await handler(event, data)
