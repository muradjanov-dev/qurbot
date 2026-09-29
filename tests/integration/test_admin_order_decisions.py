"""Admins can close the confirmation loop directly from Telegram."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import callback_admin_order_decision
from app.core.config import settings
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.shop import District, Shop
from app.db.models.user import User


async def _order_and_users(session: AsyncSession) -> tuple[Order, User, User]:
    customer = User(tg_id=700001, full_name="Customer", lang="uz_latn", role="customer")
    admin = User(tg_id=700002, full_name="Admin", lang="uz_latn", role="admin")
    district = District(region="Test", name_uz="Test", name_ru="Test")
    session.add_all([customer, admin, district])
    await session.flush()
    shop = Shop(
        name=settings.house_shop_name,
        phone=settings.house_shop_phone,
        district_id=district.id,
        address="Test",
    )
    session.add(shop)
    await session.flush()

    basket = Basket(user_id=customer.id, raw_text="fanera", status="ordered")
    session.add(basket)
    await session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("100000"),
        delivery_total=Decimal("0"),
        grand_total=Decimal("100000"),
        coverage_pct=Decimal("100"),
        shop_count=1,
    )
    session.add(quote)
    await session.flush()
    order = Order(
        quote_id=quote.id,
        user_id=customer.id,
        status="new",
        contact_phone="+998901234567",
        delivery_address="Chilonzor 9",
        grand_total_quoted=Decimal("100000"),
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderShopPart(
            order_id=order.id,
            shop_id=shop.id,
            subtotal=Decimal("100000"),
            delivery_fee=Decimal("0"),
            status="pending",
        )
    )
    await session.commit()
    return order, customer, admin


def _callback(order_id: int, action: str) -> CallbackQuery:
    message = AsyncMock(spec=Message)
    message.edit_reply_markup = AsyncMock()
    message.answer = AsyncMock()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = f"admin_order:{action}:{order_id}"
    callback.message = message
    callback.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_admin_can_confirm_an_order(test_session: AsyncSession) -> None:
    order, customer, admin = await _order_and_users(test_session)
    callback = _callback(order.id, "confirm")

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "confirmed"
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.answer.assert_awaited_once()
    notification = await test_session.scalar(
        select(OrderNotification).where(OrderNotification.order_id == order.id)
    )
    assert notification is not None
    assert notification.recipient_tg_id == customer.tg_id
    assert notification.kind == "customer_status"
    assert f"#{order.id}" in notification.text


@pytest.mark.asyncio
async def test_legacy_cancel_callback_only_opens_reason_form(test_session: AsyncSession) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    callback = _callback(order.id, "cancel")

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "new"
    assert (
        await test_session.scalar(select(OrderEvent.id).where(OrderEvent.order_id == order.id))
        is None
    )
    assert (
        await test_session.scalar(
            select(OrderNotification.id).where(OrderNotification.order_id == order.id)
        )
        is None
    )
    callback.message.edit_reply_markup.assert_awaited_once()
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == f"admin_order:confirm:{order.id}"
    assert markup.inline_keyboard[0][1].url.endswith(f"/manage/orders/{order.id}")
    assert markup.inline_keyboard[0][1].callback_data is None
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_non_admin_cannot_decide_an_order(test_session: AsyncSession) -> None:
    order, customer, _admin = await _order_and_users(test_session)
    callback = _callback(order.id, "confirm")

    await callback_admin_order_decision(
        callback=callback,
        user=customer,
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "new"
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_an_order_cannot_be_decided_twice(test_session: AsyncSession) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    order.status = "confirmed"
    await test_session.commit()
    callback = _callback(order.id, "cancel")

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "confirmed"
    assert callback.answer.await_args.kwargs["show_alert"] is True
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
