"""Regression coverage for catalogue navigation callbacks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.price_browse import callback_price_category
from app.bot.keyboards.inline import get_product_picker_keyboard


def _callback(*, has_photo: bool) -> CallbackQuery:
    message = AsyncMock(spec=Message)
    message.text = None if has_photo else "Product card"
    message.photo = [SimpleNamespace(file_id="photo")] if has_photo else None
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    message.answer = AsyncMock()

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "price_cat:7"
    callback.message = message
    callback.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
@pytest.mark.parametrize("has_photo", [False, True])
async def test_back_from_product_card_restores_the_category(
    has_photo: bool,
) -> None:
    """A Telegram photo cannot be converted into a text message with edit_text."""
    callback = _callback(has_photo=has_photo)
    session = AsyncMock(spec=AsyncSession)
    category = SimpleNamespace(id=7, name_uz="Fanera", name_ru="Fanera")
    product = SimpleNamespace(
        id=11,
        name_uz="Fanera 12 mm",
        name_ru="Fanera 12 mm",
        reference_price=None,
    )

    with (
        patch("app.bot.handlers.price_browse.CatalogRepository") as repo_type,
        patch(
            "app.bot.handlers.price_browse._cheapest_by_canonical",
            new=AsyncMock(return_value={}),
        ),
    ):
        repo = repo_type.return_value
        repo.get_category = AsyncMock(return_value=category)
        repo.list_child_categories = AsyncMock(return_value=[])
        repo.get_category_subtree_ids = AsyncMock(return_value=[7])
        repo.search_canonical_products = AsyncMock(return_value=[product])

        await callback_price_category(
            callback=callback,
            session=session,
            lang="uz_latn",
        )

    message = callback.message
    if has_photo:
        message.edit_text.assert_not_awaited()
        message.delete.assert_awaited_once()
        message.answer.assert_awaited_once()
    else:
        message.edit_text.assert_awaited_once()
        message.delete.assert_not_awaited()
        message.answer.assert_not_awaited()
        text = message.edit_text.await_args.args[0]
        assert "1. Fanera 12 mm —" in text
    callback.answer.assert_awaited_once()


def test_long_timber_name_is_full_in_message_and_identifiable_on_button() -> None:
    product = SimpleNamespace(
        id=99,
        name_uz="Taxta listvennitsa 45x140x6000 mm",
        name_uz_cyrl=None,
        name_ru="Доска лиственница 45x140x6000 мм",
    )
    markup = get_product_picker_keyboard([(product, "Kelishiladi")], lang="uz_latn")
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == "price_prod:99"
    assert "45x140x6000" in button.text
    assert len(button.text) <= 34
