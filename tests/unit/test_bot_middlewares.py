from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser

from app.bot.middlewares import (
    ErrorMiddleware,
    I18nMiddleware,
    LoggingMiddleware,
    ThrottleMiddleware,
)


@pytest.mark.asyncio
async def test_logging_middleware_attaches_correlation_id() -> None:
    middleware = LoggingMiddleware()
    handler = AsyncMock(return_value="ok")
    event = Message(
        message_id=1,
        date=1234567890,  # type: ignore[arg-type]
        chat=Chat(id=100, type="private"),
        from_user=TgUser(id=100, is_bot=False, first_name="Test"),
        text="/start",
    )
    data: dict = {}

    res = await middleware(handler, event, data)
    assert res == "ok"
    assert "correlation_id" in data
    assert len(data["correlation_id"]) == 8


@pytest.mark.asyncio
async def test_throttle_middleware_rate_limits() -> None:
    middleware = ThrottleMiddleware(limit_per_minute=2)
    handler = AsyncMock(return_value="ok")
    event = Message(
        message_id=1,
        date=1234567890,  # type: ignore[arg-type]
        chat=Chat(id=100, type="private"),
        from_user=TgUser(id=100, is_bot=False, first_name="Test"),
        text="hi",
    )
    data: dict = {}

    # Call 1: pass
    res1 = await middleware(handler, event, data)
    assert res1 == "ok"

    # Call 2: pass
    res2 = await middleware(handler, event, data)
    assert res2 == "ok"

    # Call 3: throttled (silently dropped -> returns None)
    res3 = await middleware(handler, event, data)
    assert res3 is None


@pytest.mark.asyncio
async def test_i18n_middleware_injects_translator() -> None:
    middleware = I18nMiddleware()
    handler = AsyncMock(return_value="ok")
    event = Message(
        message_id=1,
        date=1234567890,  # type: ignore[arg-type]
        chat=Chat(id=100, type="private"),
        from_user=TgUser(id=100, is_bot=False, first_name="Test"),
        text="hi",
    )
    data = {"lang": "ru"}

    res = await middleware(handler, event, data)
    assert res == "ok"
    assert "t" in data
    translate_fn = data["t"]
    assert translate_fn("btn_cancel") == "❌ Отмена"


@pytest.mark.asyncio
async def test_error_middleware_catches_unhandled_exception() -> None:
    from unittest.mock import patch

    middleware = ErrorMiddleware()
    handler = AsyncMock(side_effect=ValueError("Boom"))
    event = Message(
        message_id=1,
        date=1234567890,  # type: ignore[arg-type]
        chat=Chat(id=100, type="private"),
        from_user=TgUser(id=100, is_bot=False, first_name="Test"),
        text="hi",
    )
    data = {"lang": "uz_latn"}

    with patch.object(Message, "answer", new_callable=AsyncMock) as mock_answer:
        res = await middleware(handler, event, data)
        assert res is None
        mock_answer.assert_called_once()
