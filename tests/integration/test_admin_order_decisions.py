"""Admins can close the confirmation loop directly from Telegram."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import callback_admin_order_decision
from app.db.models.order import Basket, Order, Quote
from app.db.models.user import User


async def _order_and_users(session: AsyncSession) -> tuple[Order, User, User]:
    customer = User(tg_id=700001, full_name="Customer", lang="uz_latn", role="customer")
    admin = User(tg_id=700002, full_name="Admin", lang="uz_latn", role="admin")
    session.add_all([customer, admin])
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
@pytest.mark.parametrize(
    ("action", "expected_status"),
    [("confirm", "confirmed"), ("cancel", "cancelled")],
)
async def test_admin_can_finish_an_order(
    test_session: AsyncSession,
    action: str,
    expected_status: str,
) -> None:
    order, customer, admin = await _order_and_users(test_session)
    callback = _callback(order.id, action)
    bot = AsyncMock(spec=Bot)

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        bot=bot,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == expected_status
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.answer.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == customer.tg_id
    assert f"#{order.id}" in bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_non_admin_cannot_decide_an_order(test_session: AsyncSession) -> None:
    order, customer, _admin = await _order_and_users(test_session)
    callback = _callback(order.id, "confirm")
    bot = AsyncMock(spec=Bot)

    await callback_admin_order_decision(
        callback=callback,
        user=customer,
        session=test_session,
        bot=bot,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "new"
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_order_cannot_be_decided_twice(test_session: AsyncSession) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    order.status = "confirmed"
    await test_session.commit()
    callback = _callback(order.id, "cancel")
    bot = AsyncMock(spec=Bot)

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        bot=bot,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "confirmed"
    assert callback.answer.await_args.kwargs["show_alert"] is True
    bot.send_message.assert_not_awaited()
