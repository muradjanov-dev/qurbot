from unittest.mock import AsyncMock

import pytest

from app.bot.dispatcher import setup_bot_commands
from app.bot.handlers.webapp import launch_webapp
from app.core.config import settings


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
async def test_webapp_launch_is_inline_not_reply_keyboard(monkeypatch, lang):
    monkeypatch.setattr(settings, "storefront_webapp_url", "https://shop.example")
    message = AsyncMock()
    await launch_webapp(message, lang)
    markup = message.answer.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].web_app.url == "https://shop.example/chat"
    assert not hasattr(markup, "keyboard")


@pytest.mark.asyncio
async def test_native_menu_opens_authenticated_webapp(monkeypatch):
    monkeypatch.setattr(settings, "storefront_webapp_url", "https://shop.example")
    bot = AsyncMock()
    await setup_bot_commands(bot)
    menu = bot.set_chat_menu_button.call_args.kwargs["menu_button"]
    assert menu.type == "web_app"
    assert menu.web_app.url == "https://shop.example"


@pytest.mark.asyncio
async def test_menu_setup_failure_does_not_prevent_startup(monkeypatch):
    monkeypatch.setattr(settings, "storefront_webapp_url", "https://shop.example")
    bot = AsyncMock()
    bot.set_chat_menu_button.side_effect = RuntimeError("transport")
    await setup_bot_commands(bot)
