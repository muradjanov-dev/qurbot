from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.i18n import t


class I18nMiddleware(BaseMiddleware):
    """i18n middleware providing a pre-bound translation helper `t_func` in handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lang = data.get("lang", "uz_latn")

        # Provide a translation helper bound to the current language
        def translate(key: str, **kwargs: Any) -> str:
            return t(key, lang=lang, **kwargs)

        data["t"] = translate
        data["_"] = translate
        return await handler(event, data)
