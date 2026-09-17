from unittest.mock import patch

from aiogram.types import Chat, Message

from app.bot.handlers.ai_chat import _agent_is_available


def test_agent_filter_accepts_i18n_underscore_context() -> None:
    event = Message(
        message_id=1,
        date=1234567890,  # type: ignore[arg-type]
        chat=Chat(id=100, type="private"),
        text="fanera bormi?",
    )

    # I18nMiddleware injects `_` into handler data. The filter must accept that
    # context without binding it to the event argument a second time.
    with patch("app.bot.handlers.ai_chat.agent_available", return_value=True):
        assert _agent_is_available(event, _=lambda key: key, lang="uz_latn") is True
