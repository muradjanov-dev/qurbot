"""Retired shop-part buttons cannot bypass the admin order workflow."""

from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import callback_shop_order_decision, cmd_shop_orders
from app.core.config import settings
from app.db.models.order import OrderShopPart
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.services.order_workflow import OrderWorkflowService
from tests.integration.test_admin_order_decisions import _order_and_users


def _callback(part_id: int, action: str, *, workflow_revision: int | None = 0) -> CallbackQuery:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = (
        f"shop_order:{action}:{part_id}"
        if workflow_revision is None
        else f"shop_order:{action}:{part_id}:{workflow_revision}"
    )
    callback.message = AsyncMock(spec=Message)
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    return callback


@pytest.mark.parametrize(
    ("lang", "expected_feedback", "expected_message"),
    [
        (
            "uz_latn",
            "✅ Buyurtma #{order_id} tasdiqlandi.",
            "✅ Buyurtma <b>#{order_id}</b> operator tomonidan tasdiqlandi.",
        ),
        (
            "uz_cyrl",
            "✅ Буюртма #{order_id} тасдиқланди.",
            "✅ Буюртма <b>#{order_id}</b> оператор томонидан тасдиқланди.",
        ),
        (
            "ru",
            "✅ Заказ #{order_id} подтверждён.",
            "✅ Заказ <b>#{order_id}</b> подтверждён оператором.",
        ),
    ],
)
@pytest.mark.parametrize("workflow_revision", [0, None])
@pytest.mark.asyncio
async def test_accept_callbacks_change_parent_once_and_queue_customer_update(
    test_session: AsyncSession,
    workflow_revision: int | None,
    lang: str,
    expected_feedback: str,
    expected_message: str,
) -> None:
    order, customer, admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "accept", workflow_revision=workflow_revision)

    await callback_shop_order_decision(callback, admin, test_session, lang)
    await test_session.refresh(order)
    await test_session.refresh(part)
    assert (order.status, part.status, part.shop_response) == ("confirmed", "accepted", "accepted")
    assert len((await test_session.scalars(select(OrderEvent))).all()) == 1
    notifications = (await test_session.scalars(select(OrderNotification))).all()
    assert len(notifications) == 1 and notifications[0].recipient_tg_id == customer.tg_id
    feedback = expected_feedback.format(order_id=order.id)
    message = expected_message.format(order_id=order.id)
    callback.answer.assert_awaited_once_with(feedback)
    callback.message.edit_text.assert_awaited_once_with(message)

    stale = _callback(part.id, "accept")
    await callback_shop_order_decision(stale, admin, test_session, "uz_latn")
    assert stale.answer.await_args.kwargs["show_alert"] is True
    assert len((await test_session.scalars(select(OrderEvent))).all()) == 1


@pytest.mark.parametrize(
    ("lang", "expected_feedback"),
    [
        (
            "uz_latn",
            "Buyurtma yangilandi; joriy holatni panelda tekshiring.",
        ),
        (
            "uz_cyrl",
            "Буюртма янгиланди; жорий ҳолатни панелда текширинг.",
        ),
        ("ru", "Заказ обновлён. Проверьте его текущее состояние в панели."),
    ],
)
@pytest.mark.asyncio
async def test_old_shop_accept_callback_cannot_apply_after_order_is_reopened(
    test_session: AsyncSession, lang: str, expected_feedback: str
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    workflow = OrderWorkflowService(test_session)
    await workflow.change_status(order.id, admin, "confirmed", expected_revision=0)
    await test_session.commit()
    await workflow.change_status(
        order.id,
        admin,
        "new",
        expected_revision=1,
        reason="Reopen the order",
        correction=True,
        expected_status="confirmed",
    )
    await test_session.commit()
    callback = _callback(part.id, "accept", workflow_revision=None)

    await callback_shop_order_decision(callback, admin, test_session, lang)

    await test_session.refresh(order)
    assert order.status == "new"
    assert len((await test_session.scalars(select(OrderEvent))).all()) == 2
    assert len((await test_session.scalars(select(OrderNotification))).all()) == 2
    callback.answer.assert_awaited_once_with(expected_feedback, show_alert=True)


@pytest.mark.parametrize(
    ("lang", "expected_accept", "expected_reject"),
    [
        ("uz_latn", "✅ Qabul qilish", "❌ Rad etish"),
        ("uz_cyrl", "✅ Қабул қилиш", "❌ Рад этиш"),
        ("ru", "✅ Принять", "❌ Отклонить"),
    ],
)
@pytest.mark.asyncio
async def test_shop_orders_keyboard_carries_current_workflow_revision(
    test_session: AsyncSession, lang: str, expected_accept: str, expected_reject: str
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    order.workflow_revision = 7
    await test_session.commit()
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await cmd_shop_orders(message, admin, test_session, AsyncMock(), lang)

    message.answer.assert_awaited_once()
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    part_id = await test_session.scalar(select(OrderShopPart.id))
    assert keyboard.inline_keyboard[0][0].text == expected_accept
    assert keyboard.inline_keyboard[0][0].callback_data == f"shop_order:accept:{part_id}:7"
    assert keyboard.inline_keyboard[0][1].text == expected_reject
    assert keyboard.inline_keyboard[0][1].callback_data == f"shop_order:reject:{part_id}:7"


@pytest.mark.parametrize(
    ("lang", "expected_hint", "expected_message"),
    [
        (
            "uz_latn",
            "Bekor qilish sababini buyurtma sahifasida kiriting.",
            "❌ Buyurtma #{order_id}ni bekor qilish uchun sababni kiriting: {url}",
        ),
        (
            "uz_cyrl",
            "Бекор қилиш сабабини буюртма саҳифасида киритинг.",
            "❌ Буюртма #{order_id}ни бекор қилиш учун сабабни киритинг: {url}",
        ),
        (
            "ru",
            "Укажите причину отмены на странице заказа.",
            "❌ Чтобы отменить заказ #{order_id}, укажите причину на странице заказа: {url}",
        ),
    ],
)
@pytest.mark.asyncio
async def test_reject_callback_localizes_reason_form_feedback(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    expected_hint: str,
    expected_message: str,
) -> None:
    monkeypatch.setattr(settings, "webhook_base_url", "https://delivery.example")
    monkeypatch.setattr(settings, "storefront_webapp_url", None)
    order, _customer, admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "reject")

    await callback_shop_order_decision(callback, admin, test_session, lang)
    await test_session.refresh(order)
    assert order.status == "new" and order.cancel_reason is None
    assert not (await test_session.scalars(select(OrderEvent))).all()
    url = f"https://delivery.example/manage/orders/{order.id}"
    assert callback.message.edit_text.await_args.args[0] == expected_message.format(
        order_id=order.id, url=url
    )
    callback.answer.assert_awaited_once_with(expected_hint, show_alert=True)


@pytest.mark.asyncio
async def test_legacy_shop_button_is_admin_only(test_session: AsyncSession) -> None:
    order, customer, _admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "accept")

    await callback_shop_order_decision(callback, customer, test_session, "uz_latn")
    await test_session.refresh(order)
    assert order.status == "new"
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_shop_handler_rejects_malformed_versioned_callback(
    test_session: AsyncSession,
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    part = (await test_session.scalars(select(OrderShopPart))).one()
    callback = _callback(part.id, "accept", workflow_revision=0)
    callback.data += ":extra"

    await callback_shop_order_decision(callback, admin, test_session, "uz_latn")

    await test_session.refresh(order)
    assert order.status == "new"
    assert not (await test_session.scalars(select(OrderEvent))).all()
    assert not (await test_session.scalars(select(OrderNotification))).all()
    assert callback.answer.await_args.kwargs["show_alert"] is True
