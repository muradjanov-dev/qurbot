"""Browser-facing authorization and privacy checks for the delivery workspace."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_uzs
from app.core.config import settings
from app.core.delivery_format import format_delivery_time
from app.core.fulfillment_ui_i18n import FULFILLMENT_UI_MESSAGES
from app.core.i18n import MESSAGES
from app.core.order_delivery_i18n import ORDER_DELIVERY_MESSAGES
from app.db.models.order import Order, OrderShopPart
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.shop import Shop
from app.services.order_workflow import OrderWorkflowService
from tests.integration.test_storefront_web import (
    _basket_line,
    _checkout_fields,
    _seed,
    _sign_in,
    _sign_in_admin,
)
from tests.integration.test_storefront_web import (
    client as storefront_client,
)


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _register_delivery_test_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    # The application-level catalog registration is owned by the integrator;
    # these UI tests install both dictionaries locally without mutating i18n.py.
    for catalog in (ORDER_DELIVERY_MESSAGES, FULFILLMENT_UI_MESSAGES):
        for key, translations in catalog.items():
            monkeypatch.setitem(MESSAGES, key, translations)


async def _place_order(client: TestClient, test_session: AsyncSession) -> tuple[Any, int]:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)
    response = client.post(
        "/api/order",
        json={
            **_checkout_fields(),
            "lines": [_basket_line(data.product_id)],
            "phone": "+998901234567",
            "address_text": "Chilonzor 7",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    return data, response.json()["order_id"]


@pytest.mark.asyncio
async def test_delivery_workspace_is_admin_only_and_filters_orders(
    client: TestClient, test_session: AsyncSession
) -> None:
    data, order_id = await _place_order(client, test_session)

    customer_view = client.get("/manage/orders")
    assert customer_view.status_code == 403

    admin = await _sign_in_admin(client, test_session)
    order = await test_session.get(Order, order_id)
    assert order is not None
    await OrderWorkflowService(test_session).create_event(order, actor=admin, source="web")
    await test_session.commit()
    listing = client.get("/manage/orders?q=Test%20Mijoz&status=new")
    assert listing.status_code == 200
    assert f'href="/manage/orders/{order_id}"' in listing.text
    assert "Test Mijoz" in listing.text

    legacy = client.get(f"/shop/{data.shop_id}/orders", follow_redirects=False)
    assert legacy.status_code == 303
    assert legacy.headers["location"] == "/manage/orders"

    detail = client.get(f"/manage/orders/{order_id}")
    assert detail.status_code == 200
    assert 'action="/manage/orders/' + str(order_id) + '/status"' in detail.text
    assert 'action="/manage/orders/' + str(order_id) + '/courier"' in detail.text
    assert 'action="/manage/orders/' + str(order_id) + '/note"' in detail.text
    assert '<details class="delivery-event-details">' in detail.text
    assert '<details class="delivery-event-details" open' not in detail.text


@pytest.mark.asyncio
async def test_admin_order_list_shows_courier_and_latest_activity_ordered_first(
    client: TestClient, test_session: AsyncSession
) -> None:
    _, order_id = await _place_order(client, test_session)
    admin = await _sign_in_admin(client, test_session)
    order = await test_session.get(Order, order_id)
    assert order is not None

    event_time = order.created_at + timedelta(hours=3)
    order.updated_at = order.created_at + timedelta(hours=2)
    order.courier_name = "Courier QA Latest"
    order.courier_phone = "+99800000033"
    second = Order(
        quote_id=order.quote_id,
        user_id=order.user_id,
        status="new",
        contact_phone="+99800000044",
        contact_name="Activity QA Older",
        delivery_address="Older activity fixture",
        grand_total_quoted=Decimal("12000"),
        created_at=order.created_at + timedelta(hours=1),
        updated_at=order.created_at + timedelta(hours=1),
    )
    test_session.add(second)
    test_session.add(
        OrderEvent(
            order_id=order.id,
            actor_user_id=admin.id,
            kind="delivery_note_updated",
            from_status=order.status,
            to_status=order.status,
            reason="",
            details={"source": "test"},
            created_at=event_time,
        )
    )
    await test_session.commit()

    response = client.get("/manage/orders?status=new")
    assert response.status_code == 200
    first_position = response.text.index(f'href="/manage/orders/{order_id}"')
    second_position = response.text.index(f'href="/manage/orders/{second.id}"')
    assert first_position < second_position
    assert "Courier QA Latest" in response.text
    assert "+99800000033" in response.text
    assert format_delivery_time(event_time) in response.text


@pytest.mark.asyncio
async def test_correction_requires_explicit_target_and_legacy_partial_is_read_only(
    client: TestClient, test_session: AsyncSession
) -> None:
    _, order_id = await _place_order(client, test_session)
    await _sign_in_admin(client, test_session)

    detail = client.get(f"/manage/orders/{order_id}")
    assert detail.status_code == 200
    correction_form = detail.text.split('<details class="delivery-correction">', 1)[1].split(
        "</details>", 1
    )[0]
    assert '<option value="" disabled selected>' in correction_form
    assert '<option value="new" selected' not in correction_form

    order = await test_session.get(Order, order_id)
    assert order is not None
    order.status = "partially_fulfilled"
    await test_session.commit()
    legacy_detail = client.get(f"/manage/orders/{order_id}")
    assert legacy_detail.status_code == 200
    assert '<details class="delivery-correction">' not in legacy_detail.text
    assert FULFILLMENT_UI_MESSAGES["fulfillment_ui_legacy_status_help"]["uz_latn"] in (
        legacy_detail.text
    )


@pytest.mark.asyncio
async def test_test_admin_cannot_read_real_order_contact_details(
    client: TestClient, test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, order_id = await _place_order(client, test_session)
    admin = await _sign_in_admin(client, test_session)
    admin.is_test = True
    await test_session.commit()
    assert client.get("/manage/orders").status_code == 403
    assert client.get(f"/manage/orders/{order_id}").status_code == 403
    admin.is_test = False
    await test_session.commit()
    monkeypatch.setattr(settings, "test_tg_ids", [admin.tg_id])
    assert client.get(f"/manage/orders/{order_id}").status_code == 403


@pytest.mark.asyncio
async def test_customer_gets_public_timeline_and_courier_but_no_internal_delivery_data(
    client: TestClient, test_session: AsyncSession
) -> None:
    data, order_id = await _place_order(client, test_session)
    admin = await _sign_in_admin(client, test_session)
    order = await test_session.get(Order, order_id)
    assert order is not None

    workflow = OrderWorkflowService(test_session)
    # Checkout currently creates this event; calling the idempotent entry point
    # also keeps this UI test explicit about the public timeline's source.
    await workflow.create_event(order, actor=admin, source="web")
    await test_session.commit()

    # Missing CSRF is rejected before a delivery mutation is allowed.
    client.headers.pop("X-CSRF-Token", None)
    rejected = client.post(
        f"/manage/orders/{order_id}/note",
        data={"note": "INTERNAL NOTE: loading bay", "expected_revision": "0"},
    )
    assert rejected.status_code == 403

    _sign_in(client, admin.id, tg_id=7770001)
    saved_note = client.post(
        f"/manage/orders/{order_id}/note",
        data={
            "note": "INTERNAL NOTE: loading bay",
            "is_problem": "true",
            "expected_revision": "0",
        },
    )
    assert saved_note.status_code == 200
    assert "INTERNAL NOTE: loading bay" in saved_note.text

    stale = client.post(
        f"/manage/orders/{order_id}/note",
        data={"note": "stale edit", "expected_revision": "0"},
    )
    assert stale.status_code == 409
    assert "INTERNAL NOTE: loading bay" in stale.text
    assert "Buyurtma boshqa oynada yangilandi" in stale.text

    order = await test_session.get(Order, order_id)
    assert order is not None
    courier = client.post(
        f"/manage/orders/{order_id}/courier",
        data={
            "name": "Courier Max",
            "phone": "+998901112233",
            "vehicle": "Kia K5",
            "cost_uzs": "9876543",
            "expected_revision": str(order.workflow_revision),
        },
    )
    assert courier.status_code == 200

    order = await test_session.get(Order, order_id)
    assert order is not None
    revision = order.workflow_revision
    for expected_status, target_status in (
        ("new", "confirmed"),
        ("confirmed", "collecting"),
        ("collecting", "in_transit"),
    ):
        status_result = client.post(
            f"/manage/orders/{order_id}/status",
            data={
                "target_status": target_status,
                "expected_revision": str(revision),
                "expected_status": expected_status,
            },
        )
        assert status_result.status_code == 200
        order = await test_session.get(Order, order_id)
        assert order is not None
        revision = order.workflow_revision

    courier_changed = client.post(
        f"/manage/orders/{order_id}/courier",
        data={
            "name": "Courier Max",
            "phone": "+998901112234",
            "vehicle": "Kia K5",
            "cost_uzs": "9876543",
            "expected_revision": str(revision),
        },
    )
    assert courier_changed.status_code == 200
    order = await test_session.get(Order, order_id)
    assert order is not None
    revision = order.workflow_revision

    correction = client.post(
        f"/manage/orders/{order_id}/status",
        data={
            "target_status": "fulfilled",
            "expected_revision": str(revision),
            "expected_status": "in_transit",
            "correction": "true",
            "reason": "PRIVATE CORRECTION EXPLANATION",
        },
    )
    assert correction.status_code == 200
    assert "PRIVATE CORRECTION EXPLANATION" in correction.text
    assert "Yo‘lga chiqish xabari" in correction.text

    # Restore the customer's own session before reading their pages.
    _sign_in(client, data.user_id)
    detail = client.get(f"/orders/{order_id}")
    history = client.get("/orders")
    for response in (detail, history):
        assert response.status_code == 200
        assert "Courier Max" in response.text
        assert "+998901112234" in response.text
        assert "INTERNAL NOTE: loading bay" not in response.text
        assert "9876543" not in response.text
        assert "PRIVATE CORRECTION EXPLANATION" not in response.text
    assert "Kia K5" in detail.text
    assert "Kuryer ma’lumoti yangilandi" in detail.text
    assert "Kuryer ma’lumoti yangilandi" in history.text
    for status in ("confirmed", "in_transit", "fulfilled"):
        label = ORDER_DELIVERY_MESSAGES[f"delivery_status_{status}"]["uz_latn"]
        assert label in detail.text

    # The internal amount is an optional delivery cost, not part of the quote.
    assert Decimal(str(order.courier_cost_uzs)) == Decimal("9876543.00")


@pytest.mark.asyncio
async def test_customer_timeline_keeps_each_safe_in_transit_courier_snapshot(
    client: TestClient, test_session: AsyncSession
) -> None:
    data, order_id = await _place_order(client, test_session)
    await _sign_in_admin(client, test_session)

    order = await test_session.get(Order, order_id)
    assert order is not None
    courier_result = client.post(
        f"/manage/orders/{order_id}/courier",
        data={
            "name": "Courier Before Transit",
            "phone": "+998900000010",
            "expected_revision": str(order.workflow_revision),
        },
    )
    assert courier_result.status_code == 200
    await test_session.refresh(order)

    for expected_status, target_status in (
        ("new", "confirmed"),
        ("confirmed", "collecting"),
        ("collecting", "in_transit"),
    ):
        status_result = client.post(
            f"/manage/orders/{order_id}/status",
            data={
                "target_status": target_status,
                "expected_revision": str(order.workflow_revision),
                "expected_status": expected_status,
            },
        )
        assert status_result.status_code == 200
        await test_session.refresh(order)

    for name, phone, cost in (
        ("Courier First Snapshot", "+998900000011", "7654321"),
        ("Courier Current Snapshot", "+998900000012", "8765432"),
    ):
        courier_result = client.post(
            f"/manage/orders/{order_id}/courier",
            data={
                "name": name,
                "phone": phone,
                "cost_uzs": cost,
                "expected_revision": str(order.workflow_revision),
            },
        )
        assert courier_result.status_code == 200
        await test_session.refresh(order)

    _sign_in(client, data.user_id)
    detail = client.get(f"/orders/{order_id}")
    assert detail.status_code == 200
    public_timeline = detail.text.split('<section class="card delivery-public-timeline">', 1)[
        1
    ].split("</section>", 1)[0]
    assert "Courier First Snapshot" in public_timeline
    assert "+998900000011" in public_timeline
    assert "Courier Current Snapshot" in public_timeline
    assert "+998900000012" in public_timeline
    courier_card_start = detail.text.index('<div class="card delivery-customer-courier">')
    courier_card = detail.text[
        courier_card_start : detail.text.index(
            '<section class="card delivery-public-timeline">', courier_card_start
        )
    ]
    assert "Courier Current Snapshot" in courier_card
    assert 'href="tel:+998900000012"' in courier_card
    assert "7654321" not in detail.text
    assert "8765432" not in detail.text


@pytest.mark.asyncio
async def test_admin_can_retry_only_a_failed_order_notification(
    client: TestClient, test_session: AsyncSession
) -> None:
    _, order_id = await _place_order(client, test_session)
    admin = await _sign_in_admin(client, test_session)
    order = await test_session.get(Order, order_id)
    assert order is not None
    await OrderWorkflowService(test_session).create_event(order, actor=admin, source="web")
    await test_session.commit()

    notification = await test_session.scalar(
        select(OrderNotification).where(OrderNotification.order_id == order_id).limit(1)
    )
    assert notification is not None
    notification.status = "failed"
    notification.last_error = "temporary test failure"
    await test_session.commit()

    detail = client.get(f"/manage/orders/{order_id}")
    assert "Xato" in detail.text
    assert f"/manage/orders/{order_id}/notifications/{notification.id}/retry" in detail.text

    retried = client.post(
        f"/manage/orders/{order_id}/notifications/{notification.id}/retry",
        data={},
    )
    assert retried.status_code == 200
    assert "Navbatda" in retried.text
    await test_session.refresh(notification)
    assert notification.status == "pending"
    assert notification.last_error is None


@pytest.mark.asyncio
async def test_old_failed_fifo_head_stays_visible_and_retryable_after_recent_limit(
    client: TestClient, test_session: AsyncSession
) -> None:
    _, order_id = await _place_order(client, test_session)
    admin = await _sign_in_admin(client, test_session)
    order = await test_session.get(Order, order_id)
    assert order is not None

    recipient_tg_id = 990000001
    old_time = datetime.now(UTC) - timedelta(days=102)
    old_event = OrderEvent(
        order_id=order.id,
        actor_user_id=admin.id,
        kind="status_changed",
        from_status="new",
        to_status="new",
        reason="",
        details={},
        created_at=old_time,
    )
    test_session.add(old_event)
    await test_session.flush()
    failed_head = OrderNotification(
        event_id=old_event.id,
        order_id=order.id,
        recipient_tg_id=recipient_tg_id,
        kind="customer_status",
        text="Old failed FIFO head",
        status="failed",
        attempts=5,
        last_error="old FIFO head failure",
        created_at=old_time,
    )
    test_session.add(failed_head)

    later_times = [old_time + timedelta(days=index + 1) for index in range(101)]
    later_events = [
        OrderEvent(
            order_id=order.id,
            actor_user_id=admin.id,
            kind="status_changed",
            from_status="new",
            to_status="new",
            reason="",
            details={},
            created_at=created_at,
        )
        for created_at in later_times
    ]
    test_session.add_all(later_events)
    await test_session.flush()
    test_session.add_all(
        [
            OrderNotification(
                event_id=event.id,
                order_id=order.id,
                recipient_tg_id=recipient_tg_id,
                kind=f"later_{index:03}",
                text=f"Later row {index:03}",
                status="pending",
                created_at=later_times[index],
            )
            for index, event in enumerate(later_events)
        ]
    )
    await test_session.commit()

    detail = client.get(f"/manage/orders/{order_id}")
    assert detail.status_code == 200
    retry_path = f"/manage/orders/{order_id}/notifications/{failed_head.id}/retry"
    assert "old FIFO head failure" in detail.text
    assert retry_path in detail.text
    assert "later_100" in detail.text
    assert "later_000" not in detail.text

    retried = client.post(retry_path, data={})
    assert retried.status_code == 200
    await test_session.refresh(failed_head)
    assert failed_head.status == "pending"
    assert failed_head.attempts == 0
    assert failed_head.last_error is None


@pytest.mark.asyncio
async def test_historical_orders_are_read_only_and_keep_their_saved_total(
    client: TestClient, test_session: AsyncSession
) -> None:
    data, current_order_id = await _place_order(client, test_session)
    admin = await _sign_in_admin(client, test_session)
    current_order = await test_session.get(Order, current_order_id)
    assert current_order is not None
    house = await test_session.get(Shop, data.shop_id)
    assert house is not None

    retired_shop = Shop(
        name="Retired history partner",
        phone="+998900000099",
        district_id=house.district_id,
        address="Old partner address",
        is_active=False,
    )
    test_session.add(retired_shop)
    await test_session.flush()

    historical_time = datetime.now(UTC) - timedelta(days=365)
    historical_fields = {
        "quote_id": current_order.quote_id,
        "user_id": current_order.user_id,
        "status": "new",
        "contact_phone": "+998900000098",
        "contact_name": "Historical customer",
        "delivery_address": "Historical address",
        "grand_total_quoted": Decimal("432100.00"),
        "created_at": historical_time,
        "updated_at": historical_time,
    }
    retired_order = Order(**historical_fields)
    no_part_order = Order(
        **{
            **historical_fields,
            "contact_phone": "+998900000097",
            "delivery_address": "Historical address without shop parts",
            "grand_total_quoted": Decimal("543210.00"),
        }
    )
    test_session.add_all([retired_order, no_part_order])
    await test_session.flush()
    test_session.add(
        OrderShopPart(
            order_id=retired_order.id,
            shop_id=retired_shop.id,
            subtotal=Decimal("400000.00"),
            delivery_fee=Decimal("32100.00"),
            status="accepted",
            shop_response="accepted",
        )
    )
    historical_failure_event = OrderEvent(
        order_id=no_part_order.id,
        actor_user_id=admin.id,
        kind="status_changed",
        from_status="new",
        to_status="new",
        reason="",
        details={},
        created_at=historical_time,
    )
    test_session.add(historical_failure_event)
    await test_session.flush()
    historical_failure = OrderNotification(
        event_id=historical_failure_event.id,
        order_id=no_part_order.id,
        recipient_tg_id=990000002,
        kind="customer_status",
        text="Historical failed notification",
        status="failed",
        attempts=5,
        last_error="historical notification failure",
        created_at=historical_time,
    )
    test_session.add(historical_failure)
    await test_session.commit()

    no_part_order_id = no_part_order.id
    historical_ids_and_totals = (
        (retired_order.id, Decimal("432100.00")),
        (no_part_order_id, Decimal("543210.00")),
    )
    test_session.expire_all()
    for historical_order_id, saved_total in historical_ids_and_totals:
        detail = client.get(f"/manage/orders/{historical_order_id}")
        assert detail.status_code == 200
        assert "Bu buyurtma joriy do‘konga tegishli emas" in detail.text
        assert format_uzs(saved_total) in detail.text
        assert f'action="/manage/orders/{historical_order_id}/courier"' not in detail.text
        assert f'action="/manage/orders/{historical_order_id}/note"' not in detail.text
        assert f'action="/manage/orders/{historical_order_id}/status"' not in detail.text
        assert f"/manage/orders/{historical_order_id}/notifications/" not in detail.text
        if historical_order_id == no_part_order_id:
            assert "historical notification failure" in detail.text

        rejected = client.post(
            f"/manage/orders/{historical_order_id}/status",
            data={
                "target_status": "confirmed",
                "expected_status": "new",
                "expected_revision": "0",
            },
        )
        assert rejected.status_code == 404
        saved_order = await test_session.get(Order, historical_order_id)
        assert saved_order is not None
        assert saved_order.grand_total_quoted == saved_total
        assert saved_order.workflow_revision == 0

    listing = client.get("/manage/orders")
    assert listing.status_code == 200
    assert listing.text.count("faqat ko‘rish") == 2
    current_detail = client.get(f"/manage/orders/{current_order_id}")
    assert f'action="/manage/orders/{current_order_id}/courier"' in current_detail.text
    assert f'action="/manage/orders/{current_order_id}/note"' in current_detail.text
    assert f'action="/manage/orders/{current_order_id}/status"' in current_detail.text
