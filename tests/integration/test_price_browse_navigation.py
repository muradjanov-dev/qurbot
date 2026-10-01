"""Regression coverage for catalogue navigation callbacks."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.customer import callback_add_item, callback_calculate_quotes
from app.bot.handlers.price_browse import (
    callback_price_category,
    callback_product_detail,
    handle_product_qty,
)
from app.bot.keyboards.inline import get_product_picker_keyboard
from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.shop import District, Shop, ShopProduct
from app.services.cart_policy import assess_lines


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lang", "operator_word", "price_word", "availability_word", "false_stock_claim"),
    [
        ("uz_latn", "operator", "narx", "mavjud", "tugagan"),
        ("uz_cyrl", "оператор", "нарх", "мавжуд", "тугаган"),
        ("ru", "оператор", "цен", "налич", "нет в наличии"),
    ],
)
async def test_active_unpriced_product_card_requests_operator_confirmation(
    test_session: AsyncSession,
    lang: str,
    operator_word: str,
    price_word: str,
    availability_word: str,
    false_stock_claim: str,
) -> None:
    unit = Unit(code="dona", name_uz="dona", name_ru="шт.", dimension="count")
    category = Category(slug="timber", name_uz="Yog'och", name_ru="Древесина")
    test_session.add_all([unit, category])
    await test_session.flush()
    product = CanonicalProduct(
        slug="taxta-31x108x6000-test",
        name_uz="Taxta 31x108x6000 mm",
        name_uz_cyrl="Тахта 31x108x6000 мм",
        name_ru="Доска 31x108x6000 мм",
        category_id=category.id,
        base_unit_code=unit.code,
        search_doc="taxta 31x108x6000 mm",
        reference_price=None,
        is_active=True,
    )
    test_session.add(product)
    await test_session.flush()

    callback = _callback(has_photo=False, data=f"price_prod:{product.id}:2")
    await callback_product_detail(callback, test_session, lang)

    body = callback.message.answer.await_args.args[0]
    assert operator_word in body.lower()
    assert price_word in body.lower()
    assert availability_word in body.lower()
    assert false_stock_claim not in body.lower()
    assert settings.support_phone_text in body
    assert not any(currency in body.lower() for currency in ("so'm", "сўм", "сум"))

    buttons = {
        button.callback_data
        for row in callback.message.answer.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    }
    assert f"price_add:{product.id}" in buttons
    assert f"price_cat:{category.id}:2" in buttons

    line = {
        "line_no": 1,
        "canonical_id": product.id,
        "canonical_name": product.name_uz,
        "parsed_name": product.name_uz,
        "qty": "1",
        "unit_code": unit.code,
    }
    assessment = await assess_lines(test_session, [line])
    assert assessment[0]["requires_confirmation"] is True

    state = AsyncMock()
    state.key = SimpleNamespace(user_id=999123456)
    state.get_data = AsyncMock(return_value={"basket_lines": [line]})
    calculate_callback = _callback(has_photo=False, data="calculate_quotes")
    with patch("app.bot.handlers.guided_sales.start_request", new=AsyncMock()) as start_request:
        await callback_calculate_quotes(
            calculate_callback,
            state,
            test_session,
            SimpleNamespace(),
            lang,
        )
    start_request.assert_awaited_once()
    calculate_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_untracked_stock_accepts_large_qty_but_unavailable_products_need_confirmation(
    test_session: AsyncSession,
) -> None:
    unit = Unit(code="dona", name_uz="dona", name_ru="шт.", dimension="count")
    category = Category(slug="timber-stock", name_uz="Yog'och", name_ru="Древесина")
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    test_session.add_all([unit, category, district])
    await test_session.flush()
    shop = Shop(
        name="QurBot",
        phone="+998900000000",
        district_id=district.id,
        address="Toshkent",
        is_active=True,
    )
    test_session.add(shop)

    cases = [
        ("untracked-stock", True),
        ("out-of-stock", True),
        ("inactive-offer", True),
        ("archived-product", False),
        ("no-offer", True),
    ]
    products = {}
    for slug, is_active in cases:
        products[slug] = CanonicalProduct(
            slug=f"{slug}-test",
            name_uz=slug,
            name_uz_cyrl=slug,
            name_ru=slug,
            category_id=category.id,
            base_unit_code=unit.code,
            search_doc=slug,
            reference_price=None,
            is_active=is_active,
        )
    test_session.add_all(products.values())
    await test_session.flush()
    for slug, stock_status, is_offer_active in (
        ("untracked-stock", "in_stock", True),
        ("out-of-stock", "out", True),
        ("inactive-offer", "in_stock", False),
        ("archived-product", "in_stock", True),
    ):
        product = products[slug]
        test_session.add(
            ShopProduct(
                shop_id=shop.id,
                canonical_id=product.id,
                raw_name=product.name_uz,
                raw_unit=unit.code,
                pack_size=Decimal("1"),
                pack_unit_code=unit.code,
                price_per_pack=Decimal("10000"),
                price_per_base_unit=Decimal("10000"),
                currency="UZS",
                stock_status=stock_status,
                stock_qty=None,
                is_active=is_offer_active,
                staleness_state="fresh",
            )
        )
    await test_session.flush()

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={"pending_canonical_id": products["untracked-stock"].id}
    )
    persisted_lines: list[dict] = []

    async def persist_lines(
        state_arg: object,
        session_arg: AsyncSession,
        lines: list[dict],
    ) -> bool:
        persisted_lines.extend(dict(line) for line in lines)
        return True

    message = AsyncMock(spec=Message)
    message.text = "250000"
    message.answer = AsyncMock(
        return_value=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=5)
    )
    with (
        patch("app.bot.handlers.price_browse._load_durable_cart", new=AsyncMock(return_value=[])),
        patch("app.bot.handlers.price_browse._persist_bot_cart", new=persist_lines),
    ):
        await handle_product_qty(message, state, test_session, "uz_latn")

    assert len(persisted_lines) == 1
    assert persisted_lines[0]["qty"] == "250000"
    assert persisted_lines[0]["canonical_id"] == products["untracked-stock"].id
    assessed = await assess_lines(test_session, persisted_lines)
    assert assessed[0]["requires_confirmation"] is False
    assert assessed[0]["reference_unit_price"] == "10000.0000"

    unavailable = [
        {
            "line_no": number,
            "canonical_id": products[slug].id,
            "canonical_name": products[slug].name_uz,
            "parsed_name": products[slug].name_uz,
            "qty": "1",
            "unit_code": unit.code,
        }
        for number, slug in enumerate(
            ("out-of-stock", "inactive-offer", "archived-product", "no-offer"), start=1
        )
    ]
    guarded = await assess_lines(test_session, unavailable)
    assert [line["requires_confirmation"] for line in guarded] == [True] * 4
    assert all(line["reference_unit_price"] is None for line in guarded)


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


@pytest.mark.asyncio
async def test_basket_add_opens_catalogue_roots() -> None:
    callback = _callback(has_photo=False, data="add_item")
    state = AsyncMock()
    session = AsyncMock(spec=AsyncSession)
    roots = [
        SimpleNamespace(id=i, icon=None, name_uz=name, name_ru=name)
        for i, name in enumerate(("Plitalar", "Yog'och", "Mahkamlash"), start=1)
    ]
    with (
        patch("app.bot.handlers.customer._load_durable_cart", new=AsyncMock()) as load,
        patch("app.bot.handlers.customer.CatalogRepository") as repo_type,
    ):
        repo_type.return_value.list_root_categories = AsyncMock(return_value=roots)
        await callback_add_item(callback, state, session, "uz_latn")

    load.assert_awaited_once_with(state, session)
    markup = callback.message.answer.await_args.kwargs["reply_markup"]
    callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert {"price_cat:1", "price_cat:2", "price_cat:3"} <= callbacks
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalogue_quantity_preserves_existing_basket_and_can_repeat() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"pending_canonical_id": 22})
    session = AsyncMock(spec=AsyncSession)
    product = SimpleNamespace(id=22, name_uz="Fanera", base_unit_code="dona")
    old_line = {
        "line_no": 1,
        "canonical_id": 11,
        "canonical_name": "Sement",
        "parsed_name": "Sement",
        "qty": "3",
        "unit_code": "dona",
        "status": "auto_accept",
    }
    persisted = AsyncMock(return_value=True)
    message = AsyncMock(spec=Message)
    message.text = "2"
    message.answer = AsyncMock(
        return_value=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=5)
    )

    with (
        patch(
            "app.bot.handlers.price_browse._load_durable_cart",
            new=AsyncMock(return_value=[old_line]),
        ),
        patch("app.bot.handlers.price_browse._persist_bot_cart", new=persisted),
        patch("app.bot.handlers.price_browse.CatalogRepository") as repo_type,
    ):
        repo_type.return_value.get = AsyncMock(return_value=product)
        await handle_product_qty(message, state, session, "uz_latn")

    first_lines = persisted.await_args.args[2]
    assert [line["canonical_id"] for line in first_lines] == [11, 22]
    assert first_lines[0]["qty"] == "3"
    assert first_lines[1]["qty"] == "2"
    basket_text = message.answer.await_args.args[0]
    assert "Sement" in basket_text and "Fanera" in basket_text
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert "add_item" in {b.callback_data for row in markup.inline_keyboard for b in row}
    assert "calculate_quotes" in {b.callback_data for row in markup.inline_keyboard for b in row}

    message.text = "4"
    with (
        patch(
            "app.bot.handlers.price_browse._load_durable_cart",
            new=AsyncMock(return_value=first_lines),
        ),
        patch("app.bot.handlers.price_browse._persist_bot_cart", new=persisted),
        patch("app.bot.handlers.price_browse.CatalogRepository") as repo_type,
    ):
        repo_type.return_value.get = AsyncMock(return_value=product)
        await handle_product_qty(message, state, session, "uz_latn")

    repeated_lines = persisted.await_args.args[2]
    assert [line["canonical_id"] for line in repeated_lines] == [11, 22]
    assert repeated_lines[1]["qty"] == "6"
