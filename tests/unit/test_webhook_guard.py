"""The watchdog that keeps the bot reachable.

A missing webhook is this product's worst failure: Telegram has nowhere to
deliver, every customer message goes unanswered, and nothing anywhere errors.
These tests pin the one behaviour that matters -- it notices, and it repairs
without dropping the messages that piled up meanwhile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from aiogram.exceptions import TelegramAPIError

from app.bot.webhook_guard import assert_webhook
from app.core.config import settings


@dataclass
class FakeWebhookInfo:
    url: str
    pending_update_count: int = 0


class FakeBot:
    """Just enough Bot to answer the two calls the watchdog makes."""

    def __init__(self, url: str, *, fail_on: str | None = None) -> None:
        self.url = url
        self.fail_on = fail_on
        self.set_calls: list[dict[str, Any]] = []

    async def get_webhook_info(self) -> FakeWebhookInfo:
        if self.fail_on == "get":
            raise TelegramAPIError(method=None, message="boom")  # type: ignore[arg-type]
        return FakeWebhookInfo(url=self.url, pending_update_count=4)

    async def set_webhook(self, **kwargs: Any) -> bool:
        if self.fail_on == "set":
            raise TelegramAPIError(method=None, message="boom")  # type: ignore[arg-type]
        self.set_calls.append(kwargs)
        self.url = str(kwargs["url"])
        return True


@pytest.mark.asyncio
async def test_leaves_a_correct_registration_alone() -> None:
    bot = FakeBot(settings.webhook_url)
    assert await assert_webhook(bot) is True  # type: ignore[arg-type]
    assert bot.set_calls == []


@pytest.mark.asyncio
async def test_repairs_an_empty_webhook() -> None:
    bot = FakeBot("")
    assert await assert_webhook(bot) is False  # type: ignore[arg-type]
    assert len(bot.set_calls) == 1
    assert bot.set_calls[0]["url"] == settings.webhook_url
    assert bot.set_calls[0]["secret_token"] == settings.webhook_secret


@pytest.mark.asyncio
async def test_repair_keeps_the_messages_that_piled_up() -> None:
    """The queued updates are real customer messages, not debris.

    They arrived while the bot was unreachable and Telegram still holds them;
    dropping them on repair would turn a recovered outage into lost orders.
    """
    bot = FakeBot("")
    await assert_webhook(bot)  # type: ignore[arg-type]
    assert bot.set_calls[0]["drop_pending_updates"] is False


@pytest.mark.asyncio
async def test_repoints_a_webhook_aimed_somewhere_else() -> None:
    bot = FakeBot("https://old-deployment.example/webhook/whatever")
    assert await assert_webhook(bot) is False  # type: ignore[arg-type]
    assert bot.url == settings.webhook_url


@pytest.mark.asyncio
async def test_survives_telegram_being_unreachable() -> None:
    """A failing check must not take the web process down with it."""
    assert await assert_webhook(FakeBot("", fail_on="get")) is False  # type: ignore[arg-type]
    assert await assert_webhook(FakeBot("", fail_on="set")) is False  # type: ignore[arg-type]
