"""Regression coverage for catalogue navigation callbacks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.price_browse import callback_price_category, callback_product_detail
from app.bot.keyboards.inline import get_product_picker_keyboard


def _callback(*, has_photo: bool, data: str = "price_cat:7") -> CallbackQuery:
    message = AsyncMock(spec=Message)
    message.text = None if has_photo else "Product card"
    message.photo = [SimpleNamespace(file_id="photo")] if has_photo else None
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    message.answer = AsyncMock()

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
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
        repo.list_catalog_page = AsyncMock(return_value=([(product, None)], 1))

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


@pytest.mark.asyncio
@pytest.mark.parametrize("total", [30, 31, 65])
async def test_category_pages_cover_each_product_once(total: int) -> None:
    session = AsyncMock(spec=AsyncSession)
    category = SimpleNamespace(id=7, name_uz="Fanera", name_ru="Fanera")
    products = [
        SimpleNamespace(id=i, name_uz=f"Fanera {i}", name_ru=f"Fanera {i}", reference_price=None)
        for i in range(1, total + 1)
    ]
    seen: list[int] = []
    pages = (total + 29) // 30

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

        async def list_page(*, offset: int, limit: int, category_ids: list[int]):
            assert category_ids == [7]
            assert limit == 30
            return [(product, None) for product in products[offset : offset + limit]], total

        repo.list_catalog_page = AsyncMock(side_effect=list_page)

        for page in range(pages):
            callback = _callback(has_photo=False, data=f"price_cat:7:{page}")
            await callback_price_category(callback, session, "uz_latn")
            (text,) = callback.message.edit_text.await_args.args
            markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
            buttons = [button for row in markup.inline_keyboard for button in row]
            product_buttons = [
                button for button in buttons if button.callback_data.startswith("price_prod:")
            ]
            seen.extend(int(button.callback_data.split(":")[1]) for button in product_buttons)
            assert f"{page * 30 + 1}. Fanera" in text
            callbacks = {button.callback_data for button in buttons}
            assert (f"price_cat:7:{page - 1}" in callbacks) == (page > 0)
            assert (f"price_cat:7:{page + 1}" in callbacks) == (page + 1 < pages)
            if pages == 1:
                assert "noop" not in callbacks

    assert seen == [product.id for product in products]


@pytest.mark.asyncio
async def test_product_card_returns_to_its_category_page() -> None:
    callback = _callback(has_photo=False, data="price_prod:42:1")
    session = AsyncMock(spec=AsyncSession)
    product = SimpleNamespace(
        id=42, category_id=7, name_uz="Fanera", brand=None, base_unit_code="dona"
    )
    with (
        patch("app.bot.handlers.price_browse.CatalogRepository") as repo_type,
        patch("app.bot.handlers.price_browse.ShopRepository") as shop_type,
    ):
        repo_type.return_value.get = AsyncMock(return_value=product)
        shop_type.return_value.get_active_offers_for_canonicals = AsyncMock(return_value=[])
        shop_type.return_value.get_photo_for_canonical = AsyncMock(return_value=None)
        await callback_product_detail(callback, session, "uz_latn")

    markup = callback.message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[-1][0].callback_data == "price_cat:7:1"


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
