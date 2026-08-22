"""The watchdog that keeps the bot reachable.

A missing webhook is this product's worst failure: Telegram has nowhere to
deliver, every customer message goes unanswered, and nothing anywhere errors.
These tests pin the one behaviour that matters -- it notices, and it repairs
without dropping the messages that piled up meanwhile.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from aiogram.exceptions import TelegramAPIError

from app.bot.webhook_guard import assert_webhook, watch_webhook
from app.core.config import settings

PUBLIC_BASE_URL = "https://qurbot.example"


@pytest.fixture(autouse=True)
def _deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run these as a real deployment would.

    The guard refuses to touch the registration unless the configured URL is
    one Telegram could deliver to, and the test defaults are localhost.
    """
    monkeypatch.setattr(settings, "webhook_base_url", PUBLIC_BASE_URL)


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


@pytest.mark.asyncio
async def test_a_process_with_no_public_url_leaves_the_webhook_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure this prevents took the whole bot down.

    A service deployed without WEBHOOK_BASE_URL falls back to
    http://localhost:8000. The watchdog then finds the real deployment's
    registration, calls it lost, and tries to repoint Telegram at localhost --
    every tick, forever. Telegram happens to reject non-HTTPS URLs, so today it
    fails; a service pointed at any other valid HTTPS host would succeed and
    kill the bot silently.
    """
    monkeypatch.setattr(settings, "webhook_base_url", "http://localhost:8000")
    bot = FakeBot("https://the-real-deployment.example/webhook/real-secret")

    assert await assert_webhook(bot) is True  # type: ignore[arg-type]
    assert bot.set_calls == [], "a process that cannot host a webhook must not set one"
    assert bot.url == "https://the-real-deployment.example/webhook/real-secret"


@pytest.mark.asyncio
async def test_the_watchdog_does_not_start_without_a_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It returns instead of looping, so there is nothing to cancel."""
    monkeypatch.setattr(settings, "webhook_base_url", "http://localhost:8000")
    monkeypatch.setattr(settings, "webhook_watchdog_interval_seconds", 1)

    bot = FakeBot("https://the-real-deployment.example/webhook/real-secret")
    await asyncio.wait_for(watch_webhook(bot), timeout=2)  # type: ignore[arg-type]

    assert bot.set_calls == []


def test_only_https_counts_as_public(monkeypatch: pytest.MonkeyPatch) -> None:
    for url, expected in (
        ("https://qurbot.example", True),
        ("http://qurbot.example", False),
        ("http://localhost:8000", False),
        ("", False),
    ):
        monkeypatch.setattr(settings, "webhook_base_url", url)
        assert settings.webhook_url_is_public is expected, url
