"""Deploy notification: DM every admin_tg_id that a new version is live.

Run from Railway's preDeployCommand, after migrations, so it fires once per real
deploy. A failed notification must never fail the deploy, so every error is
swallowed after logging.
"""

import asyncio
import logging
import os

from app.bot.dispatcher import create_bot
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notify_deploy")


async def main() -> None:
    release_label = os.environ.get("RAILWAY_DEPLOYMENT_ID", "local")
    text = f"✅ QurBot deploy tugadi: <code>{release_label}</code>"

    logger.info("deploy_notify_starting admin_count=%d", len(settings.admin_tg_ids))
    bot = create_bot()
    sent = 0
    try:
        for admin_id in settings.admin_tg_ids:
            try:
                await bot.send_message(admin_id, text)
                sent += 1
            except Exception:
                # Never fail the deploy over a notification -- log and move on.
                logger.warning("deploy_notify_failed admin_id=%d", admin_id, exc_info=True)
    finally:
        await bot.session.close()
    logger.info("deploy_notify_done sent=%d/%d", sent, len(settings.admin_tg_ids))


if __name__ == "__main__":
    asyncio.run(main())
