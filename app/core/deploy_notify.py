"""Shared logic for notifying admins that a new deploy is live.

Used from app startup (reliable -- same execution context as the Telegram
setWebhook call, which is proven to work) and from scripts/notify_deploy.py
(kept for manual/CLI use).
"""

from __future__ import annotations

import logging

from aiogram import Bot

from app.core.config import settings

logger = logging.getLogger(__name__)


async def notify_admins_of_deploy(bot: Bot, release_label: str) -> int:
    """DM every admin_tg_id. Never raises -- a failed notify must never break startup."""
    text = f"✅ QurBot deploy tugadi: <code>{release_label}</code>"
    sent = 0
    for admin_id in settings.admin_tg_ids:
        try:
            await bot.send_message(admin_id, text)
            sent += 1
        except Exception:
            logger.warning("deploy_notify_failed admin_id=%d", admin_id, exc_info=True)
    logger.info("deploy_notify_done sent=%d/%d", sent, len(settings.admin_tg_ids))
    return sent
