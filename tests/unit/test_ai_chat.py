from unittest.mock import patch

from aiogram.types import Chat, Message

from app.bot.handlers.ai_chat import _agent_is_available, product_keyboard
from app.db.models.conversation import ConversationMessage


def test_product_choices_keep_full_names_and_stable_numbers() -> None:
    names = [
        "Fanera berezovaya 3x3 15 mm (1525x1525)",
        "Fanera berezovaya 2x4 15 mm (2440x1220)",
    ]
    message = ConversationMessage(
        id=42,
        cards=[{"name": name, "price_from_uzs": "100", "unit_code": "dona"} for name in names],
    )
    rows = product_keyboard(message, 7, "uz_latn").inline_keyboard
    assert all(len(row) == 1 for row in rows)
    for index, name in enumerate(names):
        assert rows[index][0].text == f"{index + 1}. {name}"
        assert rows[index][0].callback_data == f"chat:product:42:{index}:7"

    message.cards[0]["stock_unverified"] = True
    rows = product_keyboard(message, 7, "uz_latn").inline_keyboard
    assert rows[0][0].text == f"2. {names[1]}"
    assert rows[0][0].callback_data == "chat:product:42:1:7"


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
