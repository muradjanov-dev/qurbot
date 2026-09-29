"""Retired shop-part buttons cannot bypass the admin order workflow."""

from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import callback_shop_order_decision
from app.db.models.order import OrderShopPart
from app.db.models.order_workflow import OrderEvent, OrderNotification
from tests.integration.test_admin_order_decisions import _order_and_users


def _callback(part_id: int, action: str) -> CallbackQuery:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = f"shop_order:{action}:{part_id}"
    callback.message = AsyncMock(spec=Message)
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_legacy_accept_changes_parent_once_and_queues_customer_update(
    test_session: AsyncSession,
) -> None:
    order, customer, admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "accept")

    await callback_shop_order_decision(callback, admin, test_session, "uz_latn")
    await test_session.refresh(order)
    await test_session.refresh(part)
    assert (order.status, part.status, part.shop_response) == ("confirmed", "accepted", "accepted")
    assert len((await test_session.scalars(select(OrderEvent))).all()) == 1
    notifications = (await test_session.scalars(select(OrderNotification))).all()
    assert len(notifications) == 1 and notifications[0].recipient_tg_id == customer.tg_id
    callback.answer.assert_awaited_once()

    stale = _callback(part.id, "accept")
    await callback_shop_order_decision(stale, admin, test_session, "uz_latn")
    assert stale.answer.await_args.kwargs["show_alert"] is True
    assert len((await test_session.scalars(select(OrderEvent))).all()) == 1


@pytest.mark.asyncio
async def test_legacy_reject_requires_real_reason_on_web(test_session: AsyncSession) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "reject")

    await callback_shop_order_decision(callback, admin, test_session, "uz_latn")
    await test_session.refresh(order)
    assert order.status == "new" and order.cancel_reason is None
    assert not (await test_session.scalars(select(OrderEvent))).all()
    assert "/manage/orders/" in callback.message.edit_text.await_args.args[0]
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_legacy_shop_button_is_admin_only(test_session: AsyncSession) -> None:
    order, customer, _admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "accept")

    await callback_shop_order_decision(callback, customer, test_session, "uz_latn")
    await test_session.refresh(order)
    assert order.status == "new"
    assert callback.answer.await_args.kwargs["show_alert"] is True
