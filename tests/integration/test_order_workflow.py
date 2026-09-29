"""Order workflow persistence, authorization, privacy and version checks."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.order import Basket, Order, OrderItem, OrderShopPart, Quote
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.shop import District
from app.db.models.user import User
from app.services.house_shop import get_house_shop
from app.services.order_workflow import OrderWorkflowService, WorkflowError, public_order_event


async def _order(
    session: AsyncSession,
    *,
    status: str = "new",
    is_test: bool = False,
    customer_tg_id: int = 222222,
    admin_tg_id: int = 987654,
) -> tuple[Order, User, User]:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()
    house = await get_house_shop(session)
    assert house is not None
    customer = User(
        tg_id=customer_tg_id,
        full_name="Customer <Alice>",
        lang="ru",
        is_test=is_test,
    )
    admin = User(tg_id=admin_tg_id, full_name="Workflow admin", role="admin", lang="uz_cyrl")
    session.add_all([customer, admin])
    await session.flush()

    basket = Basket(user_id=customer.id, raw_text="10 dona fanera", status="ordered")
    session.add(basket)
    await session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("100000"),
        delivery_total=Decimal("10000"),
        grand_total=Decimal("110000"),
        coverage_pct=Decimal("100"),
        shop_count=1,
    )
    session.add(quote)
    await session.flush()
    order = Order(
        quote_id=quote.id,
        user_id=customer.id,
        is_test=is_test,
        status=status,
        contact_phone="+998901112233",
        contact_name=customer.full_name,
        delivery_address="A & B, Chilonzor",
        delivery_lat=Decimal("41.2856800"),
        delivery_lng=Decimal("69.2034600"),
        comment="Call before arrival",
        grand_total_quoted=Decimal("110000"),
    )
    session.add(order)
    await session.flush()
    part = OrderShopPart(
        order_id=order.id,
        shop_id=house.id,
        subtotal=Decimal("100000"),
        delivery_fee=Decimal("10000"),
        status="new",
    )
    session.add(part)
    await session.flush()
    session.add(
        OrderItem(
            order_shop_part_id=part.id,
            canonical_id=1,
            shop_product_id=1,
            qty=Decimal("10"),
            unit_code="dona",
            unit_price_quoted=Decimal("10000"),
            line_total=Decimal("100000"),
        )
    )
    await session.flush()
    return order, customer, admin


@pytest.mark.asyncio
async def test_create_event_is_idempotent_and_targets_unblocked_admins(test_session) -> None:
    order, customer, _admin = await _order(test_session)
    blocked_id = settings.admin_tg_ids[0]
    test_session.add(User(tg_id=blocked_id, role="admin", is_blocked=True))
    await test_session.flush()
    service = OrderWorkflowService(test_session)

    event = await service.create_event(order, customer, source="web")
    assert event is not None
    assert event.kind == "order_created"
    assert event.actor_user_id == customer.id

    rows = list(
        (
            await test_session.scalars(
                select(OrderNotification).where(OrderNotification.event_id == event.id)
            )
        ).all()
    )
    admin_rows = [row for row in rows if row.kind == "admin_order_created"]
    customer_rows = [row for row in rows if row.kind == "customer_order_ack"]
    recipients = {row.recipient_tg_id for row in admin_rows}
    assert blocked_id not in recipients
    assert 987654 in recipients
    assert recipients == (set(settings.admin_tg_ids) - {blocked_id}) | {987654}
    assert [(row.recipient_tg_id, row.status) for row in customer_rows] == [
        (customer.tg_id, "pending")
    ]
    assert all("A &amp; B" in row.text for row in admin_rows)
    assert all("Customer &lt;Alice&gt;" in row.text for row in admin_rows)
    assert all("#1 × 10 dona" in row.text for row in admin_rows)
    assert all("Call before arrival" in row.text for row in admin_rows)
    assert all("110 000" in row.text for row in admin_rows)
    assert all("/manage/orders/" in row.text for row in admin_rows)
    for admin_row in admin_rows:
        keyboard = admin_row.payload["reply_markup"]["inline_keyboard"]
        assert [button["callback_data"] for button in keyboard[0]] == [
            f"admin_order:confirm:{order.id}",
            f"admin_order:cancel:{order.id}",
        ]
        assert "/manage/orders/" in keyboard[1][0]["url"]

    location_rows = [row for row in rows if row.kind == "admin_order_location"]
    assert {row.recipient_tg_id for row in location_rows} == recipients
    admin_row_ids = {row.recipient_tg_id: row.id for row in admin_rows}
    for location in location_rows:
        assert location.payload == {
            "latitude": 41.28568,
            "longitude": 69.20346,
            "reply_to_notification_id": admin_row_ids[location.recipient_tg_id],
        }

    replay = await service.create_event(order, customer, source="web")
    assert replay is not None and replay.id == event.id
    assert (
        await test_session.scalar(select(OrderEvent.id).where(OrderEvent.order_id == order.id))
        == event.id
    )
    assert await test_session.scalar(
        select(func.count())
        .select_from(OrderNotification)
        .where(OrderNotification.event_id == event.id)
    ) == len(rows)


@pytest.mark.asyncio
async def test_bot_order_creation_does_not_duplicate_the_customer_receipt(test_session) -> None:
    order, customer, _admin = await _order(test_session)

    event = await OrderWorkflowService(test_session).create_event(order, customer, source="bot")

    assert event is not None
    assert (
        await test_session.scalar(
            select(OrderNotification.id).where(
                OrderNotification.event_id == event.id,
                OrderNotification.kind == "customer_order_ack",
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_status_graph_revisions_and_private_correction_reason(test_session) -> None:
    order, customer, admin = await _order(test_session)
    service = OrderWorkflowService(test_session)

    with pytest.raises(WorkflowError) as invalid:
        await service.change_status(order.id, admin, "collecting", 0)
    assert invalid.value.code == "invalid_transition"

    cancelled = await service.change_status(
        order.id,
        admin,
        "cancelled",
        0,
        reason="<b>Customer requested</b>",
    )
    assert cancelled.status == "cancelled"
    assert cancelled.workflow_revision == 1
    assert cancelled.cancel_reason == "<b>Customer requested</b>"

    events = list(
        (
            await test_session.scalars(
                select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id)
            )
        ).all()
    )
    cancel_projection = public_order_event(events[-1])
    assert cancel_projection is not None
    assert cancel_projection["public_reason"] == "<b>Customer requested</b>"
    customer_messages = list(
        (
            await test_session.scalars(
                select(OrderNotification).where(
                    OrderNotification.order_id == order.id,
                    OrderNotification.recipient_tg_id == customer.tg_id,
                )
            )
        ).all()
    )
    assert len(customer_messages) == 1
    assert "&lt;b&gt;Customer requested&lt;/b&gt;" in customer_messages[0].text
    part = await test_session.scalar(
        select(OrderShopPart).where(OrderShopPart.order_id == order.id)
    )
    assert part is not None and part.status == part.shop_response == "rejected"

    corrected = await service.change_status(
        order.id,
        admin,
        "confirmed",
        1,
        reason="Private admin correction <case>",
        correction=True,
        expected_status="cancelled",
    )
    assert corrected.status == "confirmed"
    assert corrected.workflow_revision == 2
    assert corrected.cancel_reason is None
    assert part.status == part.shop_response == "accepted"
    corrected_event = await test_session.scalar(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id, OrderEvent.kind == "status_corrected"
        )
    )
    assert corrected_event is not None
    assert corrected_event.reason == "Private admin correction <case>"
    assert public_order_event(corrected_event) is not None
    assert "public_reason" not in public_order_event(corrected_event)
    correction_message = await test_session.scalar(
        select(OrderNotification).where(
            OrderNotification.order_id == order.id,
            OrderNotification.kind == "customer_status_correction",
        )
    )
    assert correction_message is not None
    assert "Private admin correction" not in correction_message.text

    with pytest.raises(WorkflowError) as stale:
        await service.change_status(
            order.id,
            admin,
            "collecting",
            1,
            expected_status="confirmed",
        )
    assert stale.value.code == "stale_revision"
    assert stale.value.current_revision == 2

    event_count = await test_session.scalar(
        select(OrderEvent.id).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id.desc())
    )
    repeated = await service.change_status(order.id, admin, "confirmed", 2)
    assert repeated.workflow_revision == 2
    assert (
        await test_session.scalar(
            select(OrderEvent.id)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.id.desc())
        )
        == event_count
    )


@pytest.mark.asyncio
async def test_courier_gate_public_contact_outbox_and_private_delivery_notes(test_session) -> None:
    order, customer, admin = await _order(test_session)
    service = OrderWorkflowService(test_session)

    with pytest.raises(WorkflowError) as invalid_first_step:
        await service.change_status(order.id, admin, "in_transit", 0)
    assert invalid_first_step.value.code == "invalid_transition"
    await service.change_status(order.id, admin, "confirmed", 0)
    await service.change_status(order.id, admin, "collecting", 1)
    with pytest.raises(WorkflowError) as courier_required:
        await service.change_status(order.id, admin, "in_transit", 2)
    assert courier_required.value.code == "courier_required"

    order = await service.update_courier(
        order.id,
        admin,
        "Ali Valiyev",
        "+998901234567",
        "Van",
        Decimal("25000.00"),
        2,
    )
    assert order.workflow_revision == 3
    await service.change_status(order.id, admin, "in_transit", 3)

    order = await service.update_courier(
        order.id,
        admin,
        "Ali Valiyev",
        "+998909999999",
        "Van",
        Decimal("28000.00"),
        4,
    )
    assert order.workflow_revision == 5
    public_contact_event = await test_session.scalar(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id,
            OrderEvent.kind == "courier_contact_updated",
        )
    )
    assert public_contact_event is not None
    projection = public_order_event(public_contact_event)
    assert projection is not None
    assert projection["public_contact"] == {
        "courier_name": "Ali Valiyev",
        "courier_phone": "+998909999999",
    }
    contact_notice = await test_session.scalar(
        select(OrderNotification).where(
            OrderNotification.order_id == order.id,
            OrderNotification.kind == "customer_courier_contact",
        )
    )
    assert contact_notice is not None
    assert "+998909999999" in contact_notice.text
    assert "28000" not in contact_notice.text

    await service.update_note(order.id, admin, "internal dispatch note", True, 5)
    notes = await test_session.scalar(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id,
            OrderEvent.kind == "delivery_note_updated",
        )
    )
    assert notes is not None
    assert public_order_event(notes) is None
    messages = list(
        (
            await test_session.scalars(
                select(OrderNotification).where(OrderNotification.order_id == order.id)
            )
        ).all()
    )
    assert all("internal dispatch note" not in message.text for message in messages)
    assert all(message.kind != "customer_delivery_note" for message in messages)

    await service.change_status(order.id, admin, "fulfilled", 6)
    corrected = await service.change_status(
        order.id,
        admin,
        "confirmed",
        7,
        reason="Correcting a final status privately",
        correction=True,
    )
    assert corrected.status == "confirmed"
    assert corrected.workflow_revision == 8
    assert corrected.grand_total_quoted == Decimal("110000")
    all_notices = list(
        (
            await test_session.scalars(
                select(OrderNotification).where(OrderNotification.order_id == order.id)
            )
        ).all()
    )
    assert all("Correcting a final status privately" not in notice.text for notice in all_notices)


@pytest.mark.asyncio
async def test_courier_cost_respects_numeric_scale_and_precision(test_session) -> None:
    order, _customer, admin = await _order(test_session)
    service = OrderWorkflowService(test_session)

    for invalid_cost in (Decimal("1.001"), Decimal("1000000000000.00"), 12.0):
        with pytest.raises(WorkflowError) as error:
            await service.update_courier(
                order.id,
                admin,
                None,
                None,
                None,
                invalid_cost,
                0,
            )
        assert error.value.code == "invalid_courier_cost"


@pytest.mark.asyncio
async def test_manual_retry_resets_attempts_and_records_private_audit(test_session) -> None:
    order, customer, admin = await _order(test_session)
    service = OrderWorkflowService(test_session)
    event = await service.create_event(order, customer)
    assert event is not None
    notification = await test_session.scalar(
        select(OrderNotification).where(
            OrderNotification.order_id == order.id,
            OrderNotification.kind == "admin_order_created",
        )
    )
    assert notification is not None
    notification.status = "failed"
    notification.attempts = 5
    notification.last_error = "retry budget exhausted"
    await test_session.flush()

    retried = await service.retry_notification(order.id, notification.id, admin)

    assert retried.status == "pending"
    assert retried.attempts == 0
    assert retried.last_error is None
    audit = await test_session.scalar(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id,
            OrderEvent.kind == "notification_retry",
        )
    )
    assert audit is not None
    assert audit.details["notification_id"] == notification.id
    assert audit.details["previous_attempts"] == 5
    assert public_order_event(audit) is None


@pytest.mark.asyncio
async def test_legacy_partial_orders_and_test_orders_are_not_in_workflow(test_session) -> None:
    partial, _customer, admin = await _order(test_session, status="partially_fulfilled")
    with pytest.raises(WorkflowError) as partial_error:
        await OrderWorkflowService(test_session).change_status(
            partial.id,
            admin,
            "fulfilled",
            0,
            reason="legacy correction",
            correction=True,
        )
    assert partial_error.value.code == "legacy_status"

    test_order, test_customer, _test_admin = await _order(
        test_session,
        is_test=True,
        customer_tg_id=222223,
        admin_tg_id=987655,
    )
    event = await OrderWorkflowService(test_session).create_event(
        test_order, test_customer, source="web"
    )
    assert event is None
    assert (
        await test_session.scalar(select(OrderEvent.id).where(OrderEvent.order_id == test_order.id))
        is None
    )
    with pytest.raises(WorkflowError) as test_error:
        await OrderWorkflowService(test_session).change_status(test_order.id, admin, "confirmed", 0)
    assert test_error.value.code == "test_order"
