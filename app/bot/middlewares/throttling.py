import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("bot.throttle")

QUOTE_CALLBACK_DATA = "calculate_quotes"


class ThrottleMiddleware(BaseMiddleware):
    """In-memory sliding window rate limiter per user.

    Two independent buckets per SPEC §9: a general message limit, and a
    stricter limit specifically on quote (re)computation, since that's the
    expensive optimizer call.
    """

    def __init__(self, limit_per_minute: int = 20, quote_limit_per_minute: int = 3) -> None:
        self.limit_per_minute = limit_per_minute
        self.quote_limit_per_minute = quote_limit_per_minute
        self.user_timestamps: dict[int, list[float]] = defaultdict(list)
        self.quote_timestamps: dict[int, list[float]] = defaultdict(list)

    def _is_quote_request(self, event: TelegramObject) -> bool:
        return isinstance(event, CallbackQuery) and event.data == QUOTE_CALLBACK_DATA

    def _within_limit(self, history_map: dict[int, list[float]], user_id: int, limit: int) -> bool:
        now = time.time()
        window_start = now - 60.0
        history = [ts for ts in history_map[user_id] if ts > window_start]
        history_map[user_id] = history
        if len(history) >= limit:
            return False
        history_map[user_id].append(now)
        return True

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

        if self._is_quote_request(event) and not self._within_limit(
            self.quote_timestamps, user_id, self.quote_limit_per_minute
        ):
            logger.warning(
                "Throttling user %d: exceeded %d quote requests/min",
                user_id,
                self.quote_limit_per_minute,
            )
            return None

        if not self._within_limit(self.user_timestamps, user_id, self.limit_per_minute):
            logger.warning(
                "Throttling user %d: exceeded %d requests/min", user_id, self.limit_per_minute
            )
            # Silently drop flood request according to SPEC §9
            return None

        return await handler(event, data)
