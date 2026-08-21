"""DM every admin an arbitrary message -- release notes, incident notices, etc.

The message comes from argv or stdin rather than being baked in, so announcing
a release does not mean editing code and redeploying to say something new.

Usage:
    python -m scripts.notify_admins "Yangilanish: ..."
    python -m scripts.notify_admins --file notes.txt
    python -m scripts.notify_admins < notes.txt

Sends via the Telegram API, which is reachable from anywhere -- unlike the
database, this does not have to run inside the deployment.
"""

import asyncio
import logging
import pathlib
import sys

from app.bot.dispatcher import create_bot
from app.core.deploy_notify import notify_admins

logging.basicConfig(level=logging.INFO)


def _read_message() -> str:
    """Message from --file, argv, or stdin -- always decoded as UTF-8.

    The file form matters on Windows, where stdin defaults to the system code
    page and silently mangles emoji into surrogates that then fail to encode.
    """
    args = sys.argv[1:]
    if args and args[0] == "--file":
        return pathlib.Path(args[1]).read_text(encoding="utf-8").strip()
    if args:
        return " ".join(args).strip()
    return sys.stdin.buffer.read().decode("utf-8").strip()


async def main() -> None:
    text = _read_message()
    if not text:
        raise SystemExit("nothing to send: pass --file PATH, an argument, or stdin")

    bot = create_bot()
    try:
        sent = await notify_admins(bot, text)
    finally:
        await bot.session.close()
    print(f"sent to {sent} admin(s)")


if __name__ == "__main__":
    asyncio.run(main())
