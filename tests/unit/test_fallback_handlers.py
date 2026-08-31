"""Nothing a customer sends may go unanswered.

Telegram gives the sender no sign that a message went unhandled -- it simply
sits there looking delivered. Before this, a voice note, a video or a contact
card sent at the wrong moment produced exactly nothing, which is
indistinguishable from a bot that has stopped working. The people this is built
for do not try a second phrasing; they leave.
"""

from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message

from app.bot.dispatcher import dispatcher
from app.bot.handlers.fallback import msg_unhandled, msg_voice_not_supported
from app.core.config import settings


async def test_a_voice_note_gets_an_answer() -> None:
    """Older customers speak rather than type: silence here is the worst reply."""
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await msg_voice_not_supported(message, lang="uz_latn")

    sent = message.answer.call_args[0][0]
    assert settings.support_phone in sent, "give them the way that does work"
    assert "10 dona fanera 12mm" in sent, "and the format that does work"


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
async def test_every_language_has_something_to_say(lang: str) -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await msg_unhandled(message, lang=lang)

    sent = message.answer.call_args[0][0]
    assert sent.strip()
    assert settings.support_phone in sent


def test_the_fallback_router_is_registered_last() -> None:
    """It must only ever see what every real handler declined.

    Registered anywhere earlier, a catch-all swallows the wizard steps and
    basket text that later routers are waiting for.

    Asserted against the module-level dispatcher rather than a fresh one: the
    routers are singletons and can only ever be attached once.
    """
    names = [r.name for r in dispatcher.sub_routers]

    assert names[-1] == "fallback"
    assert "customer" in names and names.index("customer") < names.index("fallback")
