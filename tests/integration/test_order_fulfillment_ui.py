"""Browser-facing authorization and privacy checks for the delivery workspace."""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.fulfillment_ui_i18n import FULFILLMENT_UI_MESSAGES
from app.core.i18n import MESSAGES
from app.core.order_delivery_i18n import ORDER_DELIVERY_MESSAGES
from app.db.models.order import Order
from app.db.models.order_workflow import OrderNotification
from app.services.order_workflow import OrderWorkflowService
from tests.integration.test_storefront_web import (
    _basket_line,
    _checkout_fields,
    _seed,
    _sign_in,
    _sign_in_admin,
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

    await _sign_in_admin(client, test_session)
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

    # Restore the customer's own session before reading their pages.
    _sign_in(client, data.user_id)
    detail = client.get(f"/orders/{order_id}")
    history = client.get("/orders")
    for response in (detail, history):
        assert response.status_code == 200
        assert "Courier Max" in response.text
        assert "+998901112233" in response.text
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
