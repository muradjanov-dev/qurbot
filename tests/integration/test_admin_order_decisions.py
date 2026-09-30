"""Admins can close the confirmation loop directly from Telegram."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import callback_admin_order_decision
from app.core.config import settings
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.shop import District, Shop
from app.db.models.user import User
from app.services.order_workflow import OrderWorkflowService


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


def _callback(order_id: int, action: str, *, workflow_revision: int | None = 0) -> CallbackQuery:
    message = AsyncMock(spec=Message)
    message.edit_reply_markup = AsyncMock()
    message.answer = AsyncMock()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = (
        f"admin_order:{action}:{order_id}"
        if workflow_revision is None
        else f"admin_order:{action}:{order_id}:{workflow_revision}"
    )
    callback.message = message
    callback.answer = AsyncMock()
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
async def test_admin_can_confirm_an_order(
    test_session: AsyncSession,
    workflow_revision: int | None,
    lang: str,
    expected_feedback: str,
    expected_message: str,
) -> None:
    order, customer, admin = await _order_and_users(test_session)
    callback = _callback(order.id, "confirm", workflow_revision=workflow_revision)

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang=lang,
    )

    await test_session.refresh(order)
    assert order.status == "confirmed"
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    feedback = expected_feedback.format(order_id=order.id)
    message = expected_message.format(order_id=order.id)
    callback.answer.assert_awaited_once_with(feedback)
    callback.message.answer.assert_awaited_once_with(message)
    notification = await test_session.scalar(
        select(OrderNotification).where(OrderNotification.order_id == order.id)
    )
    assert notification is not None
    assert notification.recipient_tg_id == customer.tg_id
    assert notification.kind == "customer_status"
    assert f"#{order.id}" in notification.text


@pytest.mark.parametrize(
    ("lang", "confirm_label", "cancel_label"),
    [
        ("uz_latn", "✅ Buyurtmani tasdiqlash", "❌ Buyurtmani bekor qilish"),
        ("uz_cyrl", "✅ Буюртмани тасдиқлаш", "❌ Буюртмани бекор қилиш"),
        ("ru", "✅ Подтвердить заказ", "❌ Отменить заказ"),
    ],
)
@pytest.mark.asyncio
async def test_legacy_cancel_callback_only_opens_reason_form(
    test_session: AsyncSession, lang: str, confirm_label: str, cancel_label: str
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    callback = _callback(order.id, "cancel", workflow_revision=None)

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang=lang,
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
    assert markup.inline_keyboard[0][0].text == confirm_label
    assert markup.inline_keyboard[0][0].callback_data == f"admin_order:confirm:{order.id}:0"
    assert markup.inline_keyboard[0][1].text == cancel_label
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


@pytest.mark.parametrize(
    ("lang", "expected_feedback"),
    [
        ("uz_latn", "Buyurtma yangilandi; joriy holatni panelda tekshiring."),
        ("uz_cyrl", "Буюртма янгиланди; жорий ҳолатни панелда текширинг."),
        ("ru", "Заказ обновлён. Проверьте его текущее состояние в панели."),
    ],
)
@pytest.mark.asyncio
async def test_an_order_cannot_be_decided_twice(
    test_session: AsyncSession, lang: str, expected_feedback: str
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    order.status = "confirmed"
    await test_session.commit()
    callback = _callback(order.id, "cancel")

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang=lang,
    )

    await test_session.refresh(order)
    assert order.status == "confirmed"
    callback.answer.assert_awaited_once_with(expected_feedback, show_alert=True)
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


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
async def test_old_confirmation_callback_cannot_confirm_after_order_is_corrected_back_to_new(
    test_session: AsyncSession, lang: str, expected_feedback: str
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
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

    event_count = await test_session.scalar(
        select(func.count()).select_from(OrderEvent).where(OrderEvent.order_id == order.id)
    )
    notification_count = await test_session.scalar(
        select(func.count())
        .select_from(OrderNotification)
        .where(OrderNotification.order_id == order.id)
    )
    stale_callback = _callback(
        order.id, "confirm", workflow_revision=None
    )  # historical three-part callback

    await callback_admin_order_decision(
        callback=stale_callback,
        user=admin,
        session=test_session,
        lang=lang,
    )

    await test_session.refresh(order)
    assert order.status == "new"
    assert (
        await test_session.scalar(
            select(func.count()).select_from(OrderEvent).where(OrderEvent.order_id == order.id)
        )
        == event_count
    )
    assert (
        await test_session.scalar(
            select(func.count())
            .select_from(OrderNotification)
            .where(OrderNotification.order_id == order.id)
        )
        == notification_count
    )
    stale_callback.answer.assert_awaited_once_with(expected_feedback, show_alert=True)
    stale_callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


@pytest.mark.asyncio
async def test_admin_rejects_malformed_versioned_confirmation_callback(
    test_session: AsyncSession,
) -> None:
    order, _customer, admin = await _order_and_users(test_session)
    callback = _callback(order.id, "confirm", workflow_revision=0)
    callback.data += ":extra"

    await callback_admin_order_decision(
        callback=callback,
        user=admin,
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(order)
    assert order.status == "new"
    assert (
        await test_session.scalar(
            select(func.count()).select_from(OrderEvent).where(OrderEvent.order_id == order.id)
        )
        == 0
    )
    assert callback.answer.await_args.kwargs["show_alert"] is True
