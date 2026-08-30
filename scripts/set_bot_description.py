"""Set what Telegram shows about the bot before anyone types /start.

Two separate texts, and Telegram treats them differently:

* the **description** fills the empty chat -- the screen a first-time visitor
  reads before deciding to press Start;
* the **short description** is the bio on the bot's profile card, and it is
  what appears in search results and when the bot is forwarded.

Both are set per language, so an Uzbek phone and a Russian phone see their own.
Telegram caps them at 512 and 120 characters; this refuses rather than sends
something it knows will be truncated.

Usage:
    python -m scripts.set_bot_description          # apply
    python -m scripts.set_bot_description --show   # print what is set now
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.bot.dispatcher import create_bot

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bot_description")

DESCRIPTION_LIMIT = 512
SHORT_DESCRIPTION_LIMIT = 120

# language_code "" is the fallback Telegram uses for every locale without its
# own entry, so the Uzbek text is deliberately the default: this is an Uzbek
# marketplace first.
DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "": (
        "Bu QurBot — bozorga bormay qurilish mollarini eng sifatli va hamyonbop "
        "narxda uyingizgacha yetkazib beradigan platforma.\n\n"
        "Kerakli mollar ro'yxatini oddiy matn bilan yozing — narxini bir necha "
        "do'kon bo'yicha hisoblab, eng foydali variantni topamiz, yig'amiz va "
        "yetkazib beramiz.",
        "Bozorga bormay qurilish mollarini eng hamyonbop narxda uyingizgacha yetkazamiz.",
    ),
    "uz": (
        "Bu QurBot — bozorga bormay qurilish mollarini eng sifatli va hamyonbop "
        "narxda uyingizgacha yetkazib beradigan platforma.\n\n"
        "Kerakli mollar ro'yxatini oddiy matn bilan yozing — narxini bir necha "
        "do'kon bo'yicha hisoblab, eng foydali variantni topamiz, yig'amiz va "
        "yetkazib beramiz.",
        "Bozorga bormay qurilish mollarini eng hamyonbop narxda uyingizgacha yetkazamiz.",
    ),
    "ru": (
        "QurBot — платформа, которая привезёт стройматериалы к вам домой: "
        "качественно и по выгодной цене, без поездки на рынок.\n\n"
        "Отправьте список нужных материалов обычным текстом — посчитаем цены по "
        "нескольким магазинам, соберём самый выгодный вариант и доставим.",
        "Стройматериалы домой по выгодной цене — без поездки на рынок.",
    ),
}


def _check_limits() -> None:
    for lang, (description, short) in DESCRIPTIONS.items():
        label = lang or "default"
        if len(description) > DESCRIPTION_LIMIT:
            raise SystemExit(f"{label}: description is {len(description)} > {DESCRIPTION_LIMIT}")
        if len(short) > SHORT_DESCRIPTION_LIMIT:
            raise SystemExit(
                f"{label}: short description is {len(short)} > {SHORT_DESCRIPTION_LIMIT}"
            )


async def show() -> None:
    bot = create_bot()
    try:
        for lang in DESCRIPTIONS:
            current = await bot.get_my_description(language_code=lang or None)
            short = await bot.get_my_short_description(language_code=lang or None)
            print(f"--- {lang or 'default'} ---")
            print(f"description : {current.description!r}")
            print(f"short       : {short.short_description!r}")
    finally:
        await bot.session.close()


async def apply() -> None:
    _check_limits()
    bot = create_bot()
    try:
        for lang, (description, short) in DESCRIPTIONS.items():
            await bot.set_my_description(description=description, language_code=lang or None)
            await bot.set_my_short_description(
                short_description=short, language_code=lang or None
            )
            logger.info("set description for %s", lang or "default")
    finally:
        await bot.session.close()


def main() -> int:
    if "--show" in sys.argv[1:]:
        asyncio.run(show())
    else:
        asyncio.run(apply())
        print("bot description updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
