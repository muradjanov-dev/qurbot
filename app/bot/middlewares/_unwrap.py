"""Shared helper for outer middlewares.

Middlewares registered via `dp.update.outer_middleware(...)` receive the raw
`Update` object as `event` -- not the inner `Message`/`CallbackQuery` -- but
the same middleware classes are also unit-tested by calling them directly
with a bare `Message`/`CallbackQuery` (bypassing the dispatcher entirely).
This unwraps either shape to the inner event these middlewares actually care
about, so the same `isinstance`/`from_user` checks work in both contexts.
"""

from aiogram.types import CallbackQuery, Message, TelegramObject, Update


def unwrap_event(event: TelegramObject) -> Message | CallbackQuery | None:
    if isinstance(event, Message | CallbackQuery):
        return event
    if isinstance(event, Update):
        return event.message or event.callback_query
    return None
