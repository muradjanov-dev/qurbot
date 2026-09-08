"""Regression coverage for catalogue navigation callbacks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.price_browse import callback_price_category


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
    callback.answer.assert_awaited_once()
