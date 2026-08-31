"""The last word, so no message goes unanswered.

Telegram gives a sender no sign that a message went unhandled: it simply sits
there. So every kind of message the bot never learned to read -- a voice note,
a video, a contact card sent outside signup -- looked exactly like a broken
bot, and the customers this is built for do not try a second time, they leave.

This router is registered last, after every real handler has had its chance.
Anything reaching here is something nobody claimed, and it gets an answer that
says what to do instead.
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.core.config import settings
from app.core.i18n import t

router = Router(name="fallback")


@router.message(F.voice | F.video_note | F.audio)
async def msg_voice_not_supported(message: Message, lang: str) -> None:
    """Voice is the most likely thing to arrive and the most likely to be missed.

    Older customers speak rather than type -- it is the whole reason this
    matters -- so silence here is the worst possible answer. Until the bot can
    listen, it says so plainly and offers the two ways that do work.
    """
    await message.answer(t("fallback_voice", lang=lang, phone=settings.support_phone))


@router.message()
async def msg_unhandled(message: Message, lang: str) -> None:
    """Anything else nobody claimed: a photo, a video, a forwarded card."""
    await message.answer(t("fallback_unknown", lang=lang, phone=settings.support_phone))


@router.callback_query()
async def cb_unanswered(callback: CallbackQuery) -> None:
    """Close the loop on any button no handler answered.

    Telegram spins the button for half a minute until the callback is
    acknowledged, so a decorative one -- the "3/8" page counter between the
    arrows -- looks like a tap that is still working. Answering costs nothing
    and shows nothing.
    """
    await callback.answer()
