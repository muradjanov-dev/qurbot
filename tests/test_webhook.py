from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Update
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app

START_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1,
        "chat": {"id": 1, "type": "private"},
        "from": {"id": 1, "is_bot": False, "first_name": "Test"},
        "text": "/start",
        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
    },
}


def test_webhook_accepts_valid_update() -> None:
    with patch("aiogram.Bot.__call__", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = True
        with TestClient(app) as client:
            response = client.post(settings.webhook_path, json=START_UPDATE)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_webhook_rejects_bad_secret_header() -> None:
    with TestClient(app) as client:
        response = client.post(
            settings.webhook_path,
            json=START_UPDATE,
            headers={"x-telegram-bot-api-secret-token": "wrong"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dispatcher_reaches_start_handler_via_real_update(
    test_session: AsyncSession,
) -> None:
    """Regression test: outer middlewares registered on dp.update receive the raw
    Update object, not the inner Message -- a middleware doing
    isinstance(event, Message | CallbackQuery) against that raw Update always sees
    False, so UserContextMiddleware never set user/lang, and cmd_start crashed
    with a TypeError on every real /start (silently, since ErrorMiddleware caught
    it and itself had the same unwrapping bug, so no reply was ever sent either).

    This feeds a real Update through the actual dispatcher + full middleware
    chain, unlike test_webhook_accepts_valid_update above which only mocks the
    outbound Bot.__call__ generically and never asserts a reply was sent with the
    expected content -- exactly the gap that let this ship unnoticed.
    """
    from app.bot.dispatcher import create_bot, dispatcher

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[AsyncSession]:
        yield test_session

    with patch("app.bot.middlewares.db_session.async_session_factory", fake_session_factory):
        bot = create_bot()

        with patch("aiogram.Bot.__call__", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = True
            update = Update.model_validate(START_UPDATE)
            await dispatcher.feed_update(bot=bot, update=update)

        await test_session.commit()

    # The bug crashed cmd_start before it ever reached message.answer(...), so
    # nothing was sent -- assert the outgoing SendMessage carries the expected
    # onboarding content (language picker), not just that some call happened.
    mock_call.assert_called_once()
    sent_method = mock_call.call_args.args[0]
    assert sent_method.text is not None
    assert sent_method.reply_markup is not None
