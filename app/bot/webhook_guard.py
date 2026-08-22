"""Keeps the Telegram webhook registered while the app is running.

Registering once at startup is not enough, and the failure it misses is the
worst one this product has: with no webhook, Telegram has nowhere to deliver
to, every message goes unanswered, and nothing in the app errors -- /health
stays green while the bot is completely dead.

That is not hypothetical. Railway deploys are rolling: the new container sets
the webhook and starts serving *before* the old one shuts down, so a version
that deletes the webhook on shutdown wipes the registration the new container
just made, moments after it made it. The shutdown path no longer does that, but
a single stale container, a hand-run `deleteWebhook`, or a failed set at
startup produces the same silent outage.

So the registration is re-asserted on a timer instead of trusted. Cheap (one
getWebhookInfo per interval), idempotent, and it repairs the outage without
anyone noticing it happened -- while still logging loudly enough that someone
can find out it did.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def assert_webhook(bot: Bot) -> bool:
    """Ensure Telegram is pointing at this deployment. True if it already was.

    Never raises: a Telegram API hiccup must not take the web process down, and
    the next tick will try again.
    """
    if not settings.webhook_url_is_public:
        # This process cannot host a webhook, so it has no business deciding
        # where Telegram should point. Without this check a worker or preview
        # container started without WEBHOOK_BASE_URL fights the real web
        # service for the registration every tick.
        logger.error(
            "webhook_guard_disabled_url_not_public",
            configured=settings.webhook_base_url,
        )
        return True

    expected = settings.webhook_url
    try:
        info = await bot.get_webhook_info()
    except TelegramAPIError as exc:
        logger.warning("webhook_check_failed", error=str(exc))
        return False

    if info.url == expected:
        return True

    logger.error(
        "webhook_lost",
        found=info.url or "<empty>",
        expected=expected,
        pending=info.pending_update_count,
    )
    try:
        await bot.set_webhook(
            url=expected,
            secret_token=settings.webhook_secret,
            # Deliberately NOT dropping: these are real customer messages that
            # arrived while the bot was unreachable, and Telegram still has
            # them. Dropping would turn a recovered outage into lost orders.
            drop_pending_updates=False,
        )
    except TelegramAPIError as exc:
        logger.error("webhook_repair_failed", error=str(exc))
        return False

    logger.info("webhook_repaired", url=expected)
    return False


async def watch_webhook(bot: Bot) -> None:
    """Re-assert the webhook forever, once per configured interval.

    Runs as a background task for the lifetime of the process; cancelling it is
    the normal way it ends.
    """
    interval = settings.webhook_watchdog_interval_seconds
    if interval <= 0:
        return
    if not settings.webhook_url_is_public:
        logger.error(
            "webhook_watchdog_not_started_url_not_public",
            configured=settings.webhook_base_url,
        )
        return

    while True:
        try:
            await asyncio.sleep(interval)
            await assert_webhook(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A watchdog that dies on an unexpected error is worse than no
            # watchdog, because it looks like it is still guarding.
            logger.exception("webhook_watchdog_iteration_failed")
