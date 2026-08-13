"""Manually DM every admin that a deploy/release happened (Phase 9 hardening).

Not wired into Railway's preDeployCommand -- that execution context turned out
to have unreliable outbound networking for this call in practice, so the real
notification now fires from the app's own startup (app/main.py's lifespan,
gated on register_webhook). This script is kept for ad-hoc manual use.

Usage: python -m scripts.notify_deploy
"""

import asyncio
import logging
import os

from app.bot.dispatcher import create_bot
from app.core.deploy_notify import notify_admins_of_deploy

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    release_label = os.environ.get("RAILWAY_DEPLOYMENT_ID", "local")
    bot = create_bot()
    try:
        await notify_admins_of_deploy(bot, release_label)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
