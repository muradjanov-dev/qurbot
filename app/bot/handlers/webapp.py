"""Launch from an inline button so Telegram supplies signed identity data."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.core.config import settings
from app.core.i18n import t

router = Router(name="webapp_launch")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart(deep_link=True, magic=F.args == "webapp"))
@router.message(Command("webapp"))
@router.message(
    F.text.in_([t("open_mini_app", lang=lang) for lang in ("uz_latn", "uz_cyrl", "ru")])
)
async def launch_webapp(message: Message, lang: str) -> None:
    url = settings.storefront_webapp_url
    if not url:
        await message.answer(t("web_login_unavailable", lang=lang))
        return
    await message.answer(
        t("open_mini_app", lang=lang),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("open_mini_app", lang=lang), web_app=WebAppInfo(url=url)
                    )
                ]
            ]
        ),
    )
