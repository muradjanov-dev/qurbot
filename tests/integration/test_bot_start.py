from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    Chat,
    Message,
    MessageEntity,
    ReplyKeyboardMarkup,
    TelegramObject,
    Update,
)
from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.dispatcher import create_bot, dispatcher
from app.bot.middlewares.user_context import UserContextMiddleware
from app.bot.states import RegistrationStates
from app.core.config import settings
from app.core.i18n import DEFAULT_LANG, t
from app.db.models.cart import Cart, CartItem
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.order import Basket, Order, Quote
from app.db.models.user import User, UserAddress


def _telegram_message(tg_id: int, text: str = "/start") -> Message:
    from_user = TelegramUser(
        id=tg_id,
        is_bot=False,
        first_name="Current",
        last_name="Telegram Name",
        username="current_name",
    )
    entities = None
    if text.startswith("/"):
        command = text.split(maxsplit=1)[0]
        entities = [MessageEntity(type="bot_command", offset=0, length=len(command))]
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=tg_id, type="private"),
        from_user=from_user,
        text=text,
        entities=entities,
    )


async def _dispatch_message(
    bot: Bot, session: AsyncSession, tg_id: int, text: str = "/start"
) -> list[object]:
    update = Update(update_id=tg_id, message=_telegram_message(tg_id, text))
    with patch("aiogram.Bot.__call__", new_callable=AsyncMock) as bot_call:
        bot_call.return_value = True
        await dispatcher.feed_update(bot=bot, update=update, session=session)
    await session.flush()
    return [call.args[0] for call in bot_call.call_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
async def test_start_shows_saved_language_menu_without_a_district(
    test_session: AsyncSession, lang: str
) -> None:
    tg_id = 902_000_100 + len(lang)
    user = User(tg_id=tg_id, full_name="Saved Customer", lang=lang, district_id=None)
    test_session.add(user)
    await test_session.flush()

    bot = create_bot()
    try:
        sent = await _dispatch_message(bot, test_session, tg_id)
    finally:
        await bot.session.close()

    assert len(sent) == 1
    response = sent[0]
    assert response.text == t(
        "welcome_done",
        lang=lang,
        eta_min=settings.delivery_eta_min_hours,
        eta_max=settings.delivery_eta_max_hours,
    )
    assert isinstance(response.reply_markup, ReplyKeyboardMarkup)
    button_texts = {button.text for row in response.reply_markup.keyboard for button in row}
    assert t("menu_send_list", lang=lang) in button_texts
    assert await test_session.scalar(select(User).where(User.tg_id == tg_id)) is user
    assert user.lang == lang
    assert user.district_id is None


@pytest.mark.asyncio
async def test_start_creates_new_user_and_returns_default_language_menu(
    test_session: AsyncSession,
) -> None:
    tg_id = 902_000_200
    bot = create_bot()
    try:
        sent = await _dispatch_message(bot, test_session, tg_id)
    finally:
        await bot.session.close()

    user = await test_session.scalar(select(User).where(User.tg_id == tg_id))
    assert user is not None
    assert user.lang == DEFAULT_LANG
    assert user.district_id is None
    assert user.role == "customer"
    assert len(sent) == 1
    response = sent[0]
    assert response.text == t(
        "welcome_done",
        lang=DEFAULT_LANG,
        eta_min=settings.delivery_eta_min_hours,
        eta_max=settings.delivery_eta_max_hours,
    )
    assert isinstance(response.reply_markup, ReplyKeyboardMarkup)


@pytest.mark.asyncio
async def test_start_aliases_return_the_main_menu(test_session: AsyncSession) -> None:
    tg_id = 902_000_300
    test_session.add(User(tg_id=tg_id, full_name="Alias User", lang="uz_latn"))
    await test_session.flush()
    bot = create_bot()
    try:
        sent = await _dispatch_message(bot, test_session, tg_id, "/menu")
    finally:
        await bot.session.close()

    assert len(sent) == 1
    assert sent[0].text == t(
        "welcome_done",
        lang="uz_latn",
        eta_min=settings.delivery_eta_min_hours,
        eta_max=settings.delivery_eta_max_hours,
    )
    assert isinstance(sent[0].reply_markup, ReplyKeyboardMarkup)


@pytest.mark.asyncio
async def test_start_clears_fsm_but_preserves_account_and_customer_records(
    test_session: AsyncSession,
) -> None:
    tg_id = 902_000_400
    user = User(
        tg_id=tg_id,
        username="old_name",
        full_name="Old Name",
        lang="ru",
        district_id=None,
        role="admin",
        is_test=True,
        referral_source="web",
    )
    test_session.add(user)
    await test_session.flush()

    unit = Unit(
        code="dona",
        name_uz="dona",
        name_ru="шт.",
        dimension="count",
        factor_to_base=Decimal("1"),
    )
    category = Category(slug="start-test", name_uz="Test", name_ru="Тест")
    test_session.add_all([unit, category])
    await test_session.flush()
    product = CanonicalProduct(
        slug="start-test-product",
        name_uz="Sinov mahsuloti",
        name_uz_cyrl="Синов маҳсулоти",
        name_ru="Тестовый товар",
        category_id=category.id,
        base_unit_code=unit.code,
        search_doc="sinov mahsuloti testovyy tovar",
    )
    test_session.add(product)
    await test_session.flush()

    cart = Cart(user_id=user.id, revision=4)
    test_session.add(cart)
    await test_session.flush()
    cart_item = CartItem(
        user_id=user.id,
        canonical_id=product.id,
        qty=Decimal("2"),
        unit_code=unit.code,
    )
    address = UserAddress(
        user_id=user.id,
        label="Home",
        address_text="Saved street 12",
        lat=Decimal("41.3000000"),
        lng=Decimal("69.2000000"),
        is_default=True,
    )
    basket = Basket(user_id=user.id, raw_text="2 dona test")
    test_session.add_all([cart_item, address, basket])
    await test_session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("100000"),
        delivery_total=Decimal("0"),
        grand_total=Decimal("100000"),
        coverage_pct=Decimal("100"),
        shop_count=1,
    )
    test_session.add(quote)
    await test_session.flush()
    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        contact_phone="+998901234567",
        delivery_address="Saved street 12",
        grand_total_quoted=Decimal("100000"),
    )
    test_session.add(order)
    await test_session.flush()

    bot = create_bot()
    state = FSMContext(
        storage=dispatcher.storage,
        key=StorageKey(bot_id=bot.id, chat_id=tg_id, user_id=tg_id),
    )
    await state.set_state(RegistrationStates.waiting_for_location)
    await state.update_data(pending_lat="41.31", pending_lng="69.21")

    try:
        sent = await _dispatch_message(bot, test_session, tg_id)
    finally:
        await bot.session.close()

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert len(sent) == 1
    assert sent[0].text == t(
        "welcome_done",
        lang="ru",
        eta_min=settings.delivery_eta_min_hours,
        eta_max=settings.delivery_eta_max_hours,
    )
    assert isinstance(sent[0].reply_markup, ReplyKeyboardMarkup)
    buttons = {button.text for row in sent[0].reply_markup.keyboard for button in row}
    assert t("menu_admin_panel", lang="ru") in buttons

    await test_session.refresh(user)
    assert user.lang == "ru"
    assert user.district_id is None
    assert user.role == "admin"
    assert user.is_test is True
    assert user.referral_source == "web"
    assert await test_session.get(CartItem, (user.id, product.id)) is not None
    assert await test_session.get(UserAddress, address.id) is not None
    assert await test_session.get(Order, order.id) is not None


@pytest.mark.asyncio
async def test_user_context_uses_shared_upsert_and_preserves_existing_preferences(
    test_session: AsyncSession,
) -> None:
    tg_id = 902_000_500
    existing = User(
        tg_id=tg_id,
        username="old_name",
        full_name="Old Name",
        lang="ru",
        district_id=None,
        role="admin",
        is_test=True,
        referral_source="web",
    )
    test_session.add(existing)
    await test_session.flush()
    message = _telegram_message(tg_id, "hello")
    observed: list[dict[str, object]] = []

    async def handler(event: TelegramObject, data: dict[str, object]) -> str:
        observed.append(data)
        return "handled"

    data: dict[str, object] = {"session": test_session}
    result = await UserContextMiddleware()(handler, message, data)

    assert result == "handled"
    assert len(observed) == 1
    assert observed[0]["user"] is existing
    assert observed[0]["user_repo"] is not None
    assert observed[0]["lang"] == "ru"
    assert existing.username == "current_name"
    assert existing.full_name == "Current Telegram Name"
    assert existing.lang == "ru"
    assert existing.district_id is None
    assert existing.role == "admin"
    assert existing.is_test is True
    assert existing.referral_source == "web"
    assert existing.last_active_at is not None


@pytest.mark.asyncio
async def test_blocked_user_is_denied_before_start_handler(test_session: AsyncSession) -> None:
    tg_id = 902_000_600
    test_session.add(User(tg_id=tg_id, full_name="Blocked", is_blocked=True))
    await test_session.flush()
    bot = create_bot()
    try:
        sent = await _dispatch_message(bot, test_session, tg_id)
    finally:
        await bot.session.close()

    assert len(sent) == 1
    assert sent[0].text == "Sizning profilingiz bloklangan."
    assert sent[0].reply_markup is None
