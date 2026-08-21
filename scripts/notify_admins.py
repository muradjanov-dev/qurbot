"""DM every admin an arbitrary message -- release notes, incident notices, etc.

The message comes from argv or stdin rather than being baked in, so announcing
a release does not mean editing code and redeploying to say something new.

Usage:
    python -m scripts.notify_admins "Yangilanish: ..."
    python -m scripts.notify_admins < notes.txt

Sends via the Telegram API, which is reachable from anywhere -- unlike the
database, this does not have to run inside the deployment.
"""

import asyncio
import logging
import sys

from app.bot.dispatcher import create_bot
from app.core.deploy_notify import notify_admins

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    text = " ".join(sys.argv[1:]).strip() or sys.stdin.read().strip()
    if not text:
        raise SystemExit("nothing to send: pass a message as an argument or on stdin")

    bot = create_bot()
    try:
        sent = await notify_admins(bot, text)
    finally:
        await bot.session.close()
    print(f"sent to {sent} admin(s)")


if __name__ == "__main__":
    asyncio.run(main())
