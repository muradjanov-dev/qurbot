"""Startup behavior that protects Telegram updates during deploys."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from app.core.config import settings
from app.main import lifespan


@pytest.mark.asyncio
async def test_startup_registration_keeps_pending_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "register_webhook", True)
    monkeypatch.setattr(settings, "webhook_base_url", "https://qurbot.example")

    bot = AsyncMock()
    bot.session.close = AsyncMock()

    with (
        patch("app.main.create_bot", return_value=bot),
        patch("app.main.setup_bot_commands", new=AsyncMock()),
        patch("app.main.notify_admins_of_deploy", new=AsyncMock()),
        patch("app.main.watch_webhook", new=AsyncMock()),
        patch("app.main.logger") as logger,
    ):
        async with lifespan(FastAPI()):
            pass

    bot.set_webhook.assert_awaited_once()
    assert bot.set_webhook.await_args.kwargs["drop_pending_updates"] is False
    logger.info.assert_any_call("webhook_set")
