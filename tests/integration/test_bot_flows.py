from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.customer import (
    _serialize_variant,
    callback_calculate_quotes,
    callback_confirm_order,
    callback_select_quote,
    checkout_address,
    checkout_comment,
    handle_basket_text,
)
from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.order import Order
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User
from app.domain.optimizer.models import BasketItemQuery, DeliveryTier, ShopOffer
from app.domain.optimizer.solver import BasketOptimizer
from app.services.cart_service import CartService
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def _full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise matching across the whole catalogue, not the launch scope.

    The launch allowlist deliberately narrows what can be matched, and it has
    its own coverage in test_addresses_and_scope.py. Pinning it off here keeps
    these tests about the matching pipeline, which is what they are for --
    otherwise they would fail for a product reason rather than a code one.
    """
    monkeypatch.setattr(settings, "enabled_category_slugs", [])


@pytest.mark.asyncio
async def test_bot_full_customer_flow(test_session: AsyncSession) -> None:
    # 1. Seed database
    await seed_database(test_session)

    # The production seed does not offer OSB. Supply an explicit test offer so
    # this tests a fully priced checkout, not the now-forbidden partial order.
    from app.db.models.catalog import CanonicalProduct
    from app.db.models.shop import Shop, ShopProduct

    osb = await test_session.scalar(
        select(CanonicalProduct).where(CanonicalProduct.slug == "osb-3-9-2500-1250")
    )
    if osb is None:
        osb = await test_session.scalar(
            select(CanonicalProduct).where(CanonicalProduct.name_uz.like("%OSB%9 mm%"))
        )
    assert osb is not None
    shop = await test_session.scalar(select(Shop).where(Shop.is_active.is_(True)))
    assert shop is not None
    test_session.add(
        ShopProduct(
            shop_id=shop.id,
            canonical_id=osb.id,
            raw_name=osb.name_uz,
            raw_unit="dona",
            pack_size=Decimal("1"),
            pack_unit_code="dona",
            price_per_pack=Decimal("10000"),
            price_per_base_unit=Decimal("10000"),
            stock_status="in_stock",
            staleness_state="fresh",
        )
    )
    await test_session.commit()

    # 2. Setup user and state
    user = User(
        tg_id=987654321,
        username="tester",
        full_name="Test Customer",
        lang="uz_latn",
        district_id=1,
        role="customer",
    )
    test_session.add(user)
    await test_session.commit()

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=123, user_id=987654321)
    state = FSMContext(storage=storage, key=key)

    # 3. Simulate sending free text basket
    fake_status_msg = AsyncMock(spec=Message)
    fake_status_msg.edit_text = AsyncMock()
    fake_status_msg.delete = AsyncMock()
    fake_status_msg.answer = AsyncMock()
    fake_status_msg.chat = SimpleNamespace(id=123)
    fake_status_msg.message_id = 1
    fake_msg = AsyncMock(spec=Message)
    fake_msg.text = "10 dona fanera 12mm, 5 dona osb 9mm"
    fake_msg.answer = AsyncMock(return_value=fake_status_msg)

    # Pre-set contact phone so checkout skips phone prompt
    await state.update_data(contact_phone="+998901234567")

    await handle_basket_text(
        message=fake_msg,
        state=state,
        session=test_session,
        lang="uz_latn",
    )

    # Assert status message was sent and edited with parsed table
    fake_msg.answer.assert_called_once()
    fake_status_msg.edit_text.assert_called_once()
    table_text = fake_status_msg.edit_text.call_args[0][0]
    assert "fanera" in table_text.lower()
    assert "osb" in table_text.lower()

    # 4. Simulate clicking "Narxlarni hisoblash"
    fake_callback = AsyncMock(spec=CallbackQuery)
    fake_callback.data = "calculate_quotes"
    fake_callback.message = fake_status_msg
    fake_callback.answer = AsyncMock()

    await callback_calculate_quotes(
        callback=fake_callback,
        state=state,
        session=test_session,
        user=user,
        lang="uz_latn",
    )

    fake_status_msg.edit_text.assert_called()
    quote_card_text = fake_status_msg.edit_text.call_args[0][0]
    assert "TEJAMLI" in quote_card_text or "so'm" in quote_card_text

    # 5. Simulate selecting the first quote variant
    select_cb = AsyncMock(spec=CallbackQuery)
    select_cb.data = "select_quote:0"
    select_cb.message = fake_status_msg
    select_cb.answer = AsyncMock()

    await callback_select_quote(
        callback=select_cb,
        state=state,
        user=user,
        session=test_session,
        lang="uz_latn",
    )
    select_cb.answer.assert_awaited_once()

    # 6. Simulate entering delivery address
    addr_msg = AsyncMock(spec=Message)
    addr_msg.text = "Chilonzor 9-mavze, 12-uy"
    addr_msg.answer = AsyncMock()

    await checkout_address(
        message=addr_msg, state=state, user=user, session=test_session, lang="uz_latn"
    )
    addr_msg.answer.assert_called_once()

    # 7. Simulate entering order comment -- this now shows a review/confirm
    # screen instead of creating the order immediately.
    comment_msg = AsyncMock(spec=Message)
    comment_msg.text = "Ertaga 10:00 da yetkazib bering"
    comment_msg.answer = AsyncMock()

    await checkout_comment(
        message=comment_msg,
        state=state,
        lang="uz_latn",
    )
    comment_msg.answer.assert_called_once()
    confirm_prompt_text = comment_msg.answer.call_args[0][0]
    assert "tekshiring" in confirm_prompt_text.lower()

    # 8. Simulate tapping "Tasdiqlash" -- this is what actually creates the order
    confirm_cb = AsyncMock(spec=CallbackQuery)
    confirm_cb.data = "confirm_order"
    confirm_cb.message = fake_status_msg
    confirm_cb.answer = AsyncMock()
    fake_bot = AsyncMock()

    await callback_confirm_order(
        callback=confirm_cb,
        state=state,
        user=user,
        session=test_session,
        bot=fake_bot,
        lang="uz_latn",
    )

    # Assert Order was created in the database
    order_stmt = select(Order).where(Order.user_id == user.id)
    order_res = await test_session.execute(order_stmt)
    created_order = order_res.scalars().first()

    assert created_order is not None
    assert created_order.delivery_address == "Chilonzor 9-mavze, 12-uy"
    assert created_order.comment == "Ertaga 10:00 da yetkazib bering"
    assert created_order.grand_total_quoted > Decimal("0")
    assert len(created_order.shop_parts) >= 1


@pytest.mark.asyncio
async def test_bot_reconfirms_legacy_free_quote_at_fixed_tashkent_fee(
    test_session: AsyncSession,
) -> None:
    category = Category(slug="delivery-test", name_uz="Test", name_ru="Тест")
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    unit = Unit(code="dona", name_uz="Dona", name_ru="Шт", dimension="count")
    test_session.add_all([category, district, unit])
    await test_session.flush()
    product = CanonicalProduct(
        slug="delivery-test-product",
        name_uz="Taxta",
        name_uz_cyrl="Тахта",
        name_ru="Доска",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="taxta",
    )
    shop = Shop(
        name=settings.house_shop_name,
        phone=settings.house_shop_phone,
        district_id=district.id,
        address="Chilonzor",
        is_active=True,
    )
    user = User(tg_id=987654329, full_name="Test Customer", district_id=district.id)
    test_session.add_all([product, shop, user])
    await test_session.flush()
    offer = ShopProduct(
        shop_id=shop.id,
        canonical_id=product.id,
        raw_name="Taxta",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("6000000"),
        price_per_base_unit=Decimal("6000000"),
        stock_status="in_stock",
        staleness_state="fresh",
    )
    test_session.add(offer)
    await test_session.flush()

    item = BasketItemQuery(
        line_no=1,
        canonical_id=product.id,
        name_uz=product.name_uz,
        needed_qty=Decimal("1"),
        unit_code="dona",
    )
    stale_quote = (
        BasketOptimizer(
            [item],
            [
                ShopOffer(
                    offer_id=offer.id,
                    shop_id=shop.id,
                    shop_name=shop.name,
                    canonical_id=product.id,
                    price_uzs=Decimal("6000000"),
                    pack_size=Decimal("1"),
                    pack_unit="dona",
                    in_stock=True,
                    stock_status="in_stock",
                    staleness_state="fresh",
                    tier="standard",
                    brand_name=None,
                    trust_score=1.0,
                    eta_hours=24,
                    is_active=True,
                )
            ],
            {
                shop.id: DeliveryTier(
                    shop_id=shop.id,
                    district_id=district.id,
                    base_fee_uzs=Decimal("50000"),
                    free_above_uzs=Decimal("5000000"),
                    min_order_uzs=Decimal("0"),
                    eta_hours=24,
                )
            },
        )
        .solve()
        .deduplicated_variants[0]
    )
    assert stale_quote.grand_total_uzs == Decimal("6000000")

    snapshot = await CartService(test_session).set_item(
        user.id,
        product.id,
        "1",
        expected_revision=0,
        unit_code="dona",
    )
    await test_session.commit()

    state = FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=124, user_id=user.tg_id),
    )
    await state.update_data(
        delivery_address="Chilonzor 7",
        contact_phone="+998901234567",
        quotes=[_serialize_variant(stale_quote)],
        selected_quote_idx=0,
        quote_cart_revision=snapshot.revision,
        cart_revision=snapshot.revision,
        delivery_district_id=district.id,
        checkout_key="stale-free-delivery",
    )
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = message
    callback.answer = AsyncMock()

    await callback_confirm_order(
        callback=callback,
        state=state,
        user=user,
        session=test_session,
        bot=AsyncMock(),
        lang="uz_latn",
    )

    assert await test_session.scalar(select(Order.id)) is None
    updated = await state.get_data()
    assert Decimal(updated["quotes"][0]["delivery_total_uzs"]) == Decimal("50000")
    assert Decimal(updated["quotes"][0]["grand_total_uzs"]) == Decimal("6050000")
    assert "50 000" in message.answer.await_args.args[0]
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_basket_text_with_no_product_list_gets_usage_guidance(
    test_session: AsyncSession,
) -> None:
    """A greeting/question with no qty+unit pattern should guide the user, not
    show a confusing parse table full of fabricated qty=1 lines (SPEC §9)."""
    await seed_database(test_session)

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=124, user_id=555555555)
    state = FSMContext(storage=storage, key=key)

    fake_status_msg = AsyncMock(spec=Message)
    fake_status_msg.edit_text = AsyncMock()
    fake_msg = AsyncMock(spec=Message)
    fake_msg.text = "Salom, bot qanday ishlaydi?"
    fake_msg.answer = AsyncMock(return_value=fake_status_msg)

    await handle_basket_text(
        message=fake_msg,
        state=state,
        session=test_session,
        lang="uz_latn",
    )

    fake_status_msg.edit_text.assert_called_once()
    guidance_text = fake_status_msg.edit_text.call_args[0][0]
    assert "tushunmadim" in guidance_text.lower()
    assert "fanera" in guidance_text.lower()


@pytest.mark.asyncio
async def test_unparseable_message_prefers_the_model_s_guidance(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the model answers, the customer gets its words, not the fixed string.

    The fallback above is the floor, not the intent: a fixed "tushunmadim" tells
    someone who wrote a greeting nothing they can act on.
    """
    from app.services.catalog_service import CatalogService

    guidance = "Salom! 10 dona fanera 12mm ko'rinishida yozing."

    async def _guide(self: CatalogService, message_text: str, lang: str = "uz_latn") -> str:
        return guidance

    monkeypatch.setattr(CatalogService, "guide_customer", _guide)
    await seed_database(test_session)

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=125, user_id=555555556))

    fake_status_msg = AsyncMock(spec=Message)
    fake_status_msg.edit_text = AsyncMock()
    fake_msg = AsyncMock(spec=Message)
    fake_msg.text = "Salom, bot qanday ishlaydi?"
    fake_msg.answer = AsyncMock(return_value=fake_status_msg)

    await handle_basket_text(
        message=fake_msg,
        state=state,
        session=test_session,
        lang="uz_latn",
    )

    sent = fake_status_msg.edit_text.call_args[0][0]
    assert guidance in sent
    assert "tushunmadim" not in sent.lower()
