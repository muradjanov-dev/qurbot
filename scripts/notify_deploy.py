"""Deploy notification: DM every admin_tg_id that a new version is live.

Run from Railway's preDeployCommand, after migrations, so it fires once per real
deploy. A failed notification must never fail the deploy, so every error is
swallowed after logging.
"""

import asyncio
import logging
import os

from aiogram.exceptions import TelegramAPIError

from app.bot.dispatcher import create_bot
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notify_deploy")


async def main() -> None:
    release_label = os.environ.get("RAILWAY_DEPLOYMENT_ID", "local")
    text = f"✅ QurBot deploy tugadi: <code>{release_label}</code>"

    bot = create_bot()
    try:
        for admin_id in settings.admin_tg_ids:
            try:
                await bot.send_message(admin_id, text)
            except TelegramAPIError as exc:
                logger.warning(
                    "deploy_notify_failed", extra={"admin_id": admin_id, "error": str(exc)}
                )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
