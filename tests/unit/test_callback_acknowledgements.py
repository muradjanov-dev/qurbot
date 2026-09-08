"""Inline buttons must stop Telegram's loading spinner on stale state too."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.customer import callback_calculate_quotes, callback_nav_quote


def _callback(data: str) -> CallbackQuery:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.message = message
    callback.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_calculate_quotes_acknowledges_an_expired_basket() -> None:
    callback = _callback("calculate_quotes")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    await callback_calculate_quotes(
        callback=callback,
        state=state,
        session=AsyncMock(spec=AsyncSession),
        user=SimpleNamespace(district_id=1),
        lang="uz_latn",
    )

    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_quote_navigation_acknowledges_an_expired_carousel() -> None:
    callback = _callback("nav_quote:0")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    await callback_nav_quote(
        callback=callback,
        state=state,
        session=AsyncMock(spec=AsyncSession),
        lang="uz_latn",
    )

    callback.answer.assert_awaited_once()
