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
    callback_calculate_quotes,
    callback_confirm_order,
    callback_select_quote,
    checkout_address,
    checkout_comment,
    handle_basket_text,
)
from app.core.config import settings
from app.db.models.order import Order
from app.db.models.user import User
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
    fake_msg.text = "500 kg cement m400, 500 dona g'isht"
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
    assert "Sement" in table_text or "sement" in table_text
    assert "g'isht" in table_text or "G'isht" in table_text

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

    await callback_select_quote(
        callback=select_cb,
        state=state,
        user=user,
        session=test_session,
        lang="uz_latn",
    )

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
    assert "qop sement" in guidance_text.lower()
