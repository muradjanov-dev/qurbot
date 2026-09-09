"""The public contact screen must expose every configured support number."""

from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message

from app.bot.handlers.common import menu_contact
from app.core.config import settings


@pytest.mark.asyncio
async def test_contact_menu_lists_all_support_numbers_without_names() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await menu_contact(message=message, lang="uz_latn")

    sent = message.answer.await_args.args[0]
    for phone in settings.support_phones:
        assert phone in sent
    assert "Sunnatilloh" not in sent
    assert "Abdumavlon" not in sent
