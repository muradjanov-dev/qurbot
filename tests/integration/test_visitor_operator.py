"""Guest ownership, authenticated operator workflow, and anonymous checkout."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import settings
from app.db.models.conversation import ConversationNotification
from app.db.models.order import Order
from app.db.models.shop import District, ShopDeliveryRule
from app.db.models.user import User, VisitorSession
from app.db.session import get_db_session
from app.main import create_app
from app.services.conversation_service import ConversationService
from app.web.storefront import visitor
from app.web.storefront.routers import chat as chat_routes
from app.web.storefront.security import csrf_token
from app.web.storefront.session import GUEST_COOKIE, SESSION_COOKIE, sign_session
from tests.integration.test_storefront_web import _seed


def headers(client):
    raw = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    request = Request({"type": "http", "headers": [(b"cookie", raw.encode())]})
    return {"X-CSRF-Token": csrf_token(request), "Origin": "https://shop.test"}


@pytest.fixture
async def web(test_session, monkeypatch):
    limiter = AsyncMock()
    monkeypatch.setattr(visitor, "limit", limiter)
    monkeypatch.setattr(chat_routes, "limit", limiter)
    # Never depend on a developer's Redis to make this API fixture pass.
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(settings, "admin_tg_ids", [])
    monkeypatch.setattr(settings, "enabled_category_slugs", [])
    monkeypatch.setattr(settings, "llm_enabled", False)
    app = create_app()

    async def override() -> AsyncIterator[AsyncSession]:
        yield test_session
        await test_session.commit()

    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.test"
    ) as client:
        yield client, app


async def bootstrap(client):
    response = await client.post("/api/session", headers={"X-QurBot-Bootstrap": "1"})
    assert response.status_code == 200
    assert response.json()["mode"] == "guest"


async def test_guest_session_ownership_csrf_and_expiry(web, test_session):
    client, app = web
    assert (await client.post("/api/session")).status_code == 403
    await bootstrap(client)
    token = client.cookies.get(GUEST_COOKIE)
    session = await test_session.get(VisitorSession, sha256(token.encode()).hexdigest())
    user = await test_session.get(User, session.user_id)
    assert user.tg_id is None and user.role == "customer"
    await bootstrap(client)
    assert await test_session.scalar(select(func.count()).select_from(VisitorSession)) == 1
    assert (await client.get("/operator")).status_code == 303
    assert (await client.get("/api/chat/operator")).status_code == 403
    assert (
        await client.post("/api/chat/messages", json={"text": "secret", "request_id": "one"})
    ).status_code == 403
    response = await client.post(
        "/api/chat/messages", json={"text": "secret", "request_id": "one"}, headers=headers(client)
    )
    assert response.status_code == 202
    job = response.json()["job_id"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://shop.test") as other:
        await bootstrap(other)
        assert (await other.get(f"/api/chat/jobs/{job}")).status_code == 404
        assert not (await other.get("/api/chat")).json()["messages"]
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await test_session.commit()
    assert (await client.get("/api/chat")).status_code == 401


@pytest.mark.parametrize("role", ["admin", "configured_admin", "customer", "guest", "blocked"])
async def test_operator_entry_points_are_role_scoped(web, test_session, monkeypatch, role):
    client, _ = web
    if role == "guest":
        await bootstrap(client)
    else:
        user = User(
            tg_id=992211,
            role="admin" if role in {"admin", "blocked"} else "customer",
            is_blocked=role == "blocked",
        )
        test_session.add(user)
        await test_session.commit()
        if role == "configured_admin":
            monkeypatch.setattr(settings, "admin_tg_ids", [user.tg_id])
        client.cookies.set(SESSION_COOKIE, sign_session(user_id=user.id, tg_id=user.tg_id))
    admin = role in {"admin", "configured_admin"}
    for path in ["/", "/catalog", "/basket", "/orders", "/account"]:
        response = await client.get(path)
        assert ("data-operator-shortcut" in response.text) is admin
        if path == "/account":
            assert ("data-account-inbox" in response.text) is admin
            assert ("data-admin-login" in response.text) is (role == "guest")
    chat = await client.get("/chat")
    assert ('href="/operator"' in chat.text) is admin
    inbox = await client.get("/operator")
    assert (inbox.status_code == 200) is admin


async def test_inbox_consent_claim_read_close_and_notification_channel(web, test_session):
    client, _ = web
    await bootstrap(client)
    snapshot = (await client.get("/api/chat")).json()
    conversation_id = snapshot["conversation_id"]
    admin = User(tg_id=12344, role="admin")
    test_session.add(admin)
    await test_session.commit()
    service = ConversationService(test_session)
    assert await service.queue(admin) == []
    response = await client.post("/api/chat/handoff", json={}, headers=headers(client))
    assert response.status_code == 200
    assert chat_routes.limit.await_args.args[1:] == ("handoff:127.0.0.1", 20, 3600)
    await client.post("/api/chat/handoff", json={}, headers=headers(client))
    await client.post(
        "/api/chat/messages", json={"text": "help", "request_id": "human"}, headers=headers(client)
    )
    assert (
        await test_session.scalar(select(func.count()).select_from(ConversationNotification)) == 1
    )
    client.cookies.set(SESSION_COOKIE, sign_session(user_id=admin.id, tg_id=admin.tg_id))
    assert (await client.get("/operator")).status_code == 200
    queue = (await client.get("/api/chat/operator")).json()["conversations"]
    assert queue[0]["unread"] == 1
    claimed = await client.post(
        f"/api/chat/operator/{conversation_id}/claim", json={}, headers=headers(client)
    )
    assert claimed.status_code == 200
    await client.post(
        f"/api/chat/operator/{conversation_id}/read",
        json={"sequence": 99999},
        headers=headers(client),
    )
    assert (await client.get("/api/chat/operator")).json()["conversations"][0]["unread"] == 0
    reply = await client.post(
        f"/api/chat/operator/{conversation_id}/messages",
        json={"text": "hello", "request_id": "reply"},
        headers=headers(client),
    )
    assert reply.status_code == 200
    # Guest messages never turn into Telegram notifications addressed to None.
    assert (
        await test_session.scalar(select(func.count()).select_from(ConversationNotification)) == 1
    )
    assert (
        await client.post(
            f"/api/chat/operator/{conversation_id}/close", json={}, headers=headers(client)
        )
    ).status_code == 200
    assert (await client.get("/api/chat/operator")).json()["conversations"] == []
    assert (await client.get(f"/api/chat/operator/{conversation_id}")).status_code == 404


async def test_guest_checkout_has_live_delivery_and_replay(web, test_session):
    client, _ = web
    fixtures = await _seed(test_session)
    await bootstrap(client)
    await client.put(
        f"/api/cart/items/{fixtures.product_id}",
        json={"qty": "2", "unit_code": "dona", "expected_revision": 0},
        headers=headers(client),
    )
    cart = (await client.get("/api/cart")).json()
    district = await test_session.scalar(select(District.id))
    body = {
        "contact_name": "Guest buyer",
        "phone": "+998901234567",
        "address_text": "Test street 12",
        "district_id": district,
        "cart_revision": cart["revision"],
        "idempotency_key": "checkout-one",
    }
    preview = (
        await client.post("/api/checkout/preview", json=body, headers=headers(client))
    ).json()
    assert preview["ok"], preview
    body["expected_total"] = preview["variant"]["grand_total_raw"]
    body["strategy"] = preview["variant"]["strategy"]
    response = await client.post("/api/order", json=body, headers=headers(client))
    assert response.json()["ok"], response.text
    order_id = response.json()["order_id"]
    again = await client.post("/api/order", json=body, headers=headers(client))
    assert again.json()["order_id"] == order_id and again.json()["replayed"]
    order = await test_session.get(Order, order_id)
    assert order.contact_name == "Guest buyer"
    assert "Chilonzor" in order.delivery_address and "Test street 12" in order.delivery_address
    assert (await test_session.get(User, order.user_id)).tg_id is None
    assert (await client.get(f"/orders/{order_id}")).status_code == 200


async def test_guest_cannot_upgrade_role_or_set_test_marker(web, test_session):
    client, _ = web
    await bootstrap(client)
    token = client.cookies.get(GUEST_COOKIE)
    row = await test_session.get(VisitorSession, sha256(token.encode()).hexdigest())
    user = await test_session.get(User, row.user_id)
    assert not user.is_test
    user.role = "admin"  # Even an incorrectly provisioned guest is not an admin identity.
    await test_session.commit()
    assert (await client.get("/api/chat/operator")).status_code == 403
    assert (await client.get("/operator")).status_code == 303


@pytest.mark.parametrize("kind", ["missing", "pickup_only"])
async def test_unconfirmed_delivery_cannot_be_ordered(web, test_session, kind):
    client, _ = web
    fixture = await _seed(test_session)
    district = await test_session.scalar(select(District.id))
    if kind == "missing":
        other = District(region="Test", name_uz="Other", name_ru="Other")
        test_session.add(other)
        await test_session.flush()
        district = other.id
    else:
        rule = await test_session.scalar(select(ShopDeliveryRule))
        rule.is_pickup_only = True
    await test_session.commit()
    await bootstrap(client)
    result = await client.put(
        f"/api/cart/items/{fixture.product_id}",
        json={"qty": "2", "unit_code": "dona", "expected_revision": 0},
        headers=headers(client),
    )
    body = {
        "contact_name": "Guest",
        "phone": "+998901234567",
        "address_text": "Test street 12",
        "district_id": district,
        "cart_revision": result.json()["revision"],
        "idempotency_key": "no-delivery",
        "expected_total": "116000",
    }
    preview = await client.post("/api/checkout/preview", json=body, headers=headers(client))
    assert preview.json()["requires_confirmation"] is True
    order = await client.post("/api/order", json=body, headers=headers(client))
    assert not order.json()["ok"]
    assert await test_session.scalar(select(func.count()).select_from(Order)) == 0


async def test_human_replies_follow_customer_channel(web, test_session):
    client, _ = web
    customer = User(tg_id=82920)
    admin = User(tg_id=82921, role="admin")
    test_session.add_all([customer, admin])
    await test_session.flush()
    service = ConversationService(test_session)
    data = await service.handoff(customer, channel="telegram")
    await service.claim(admin, data["id"])
    await service.operator_reply(admin, data["id"], "bot reply", "one")
    await test_session.flush()
    count = await test_session.scalar(select(func.count()).select_from(ConversationNotification))
    await service.submit(customer, "now on web", "web-message", channel="web")
    await service.operator_reply(admin, data["id"], "web reply", "two")
    await test_session.flush()
    assert (
        await test_session.scalar(select(func.count()).select_from(ConversationNotification))
        == count
    )


@pytest.mark.parametrize(
    "peer,forwarded,expected",
    [
        ("198.51.100.1", "203.0.113.5", "198.51.100.1"),
        ("172.18.0.3", "spoofed, 198.51.100.1", "198.51.100.1"),
        ("172.18.0.3", "invalid", "172.18.0.3"),
    ],
)
def test_guest_limit_trusts_only_proxy_hops(peer, forwarded, expected, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_networks", ["172.16.0.0/12"])
    request = Request(
        {
            "type": "http",
            "client": (peer, 123),
            "headers": [(b"x-forwarded-for", forwarded.encode())],
        }
    )
    assert visitor.ip_key(request) == expected


@pytest.mark.parametrize("outcome,status", [(1, None), (0, 429), (RuntimeError("offline"), 503)])
async def test_guest_limiter_denies_exhausted_or_unavailable_redis(monkeypatch, outcome, status):
    redis = AsyncMock()
    if isinstance(outcome, Exception):
        redis.eval.side_effect = outcome
    else:
        redis.eval.return_value = outcome
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=redis)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(visitor.Redis, "from_url", lambda *args, **kwargs: context)
    request = Request({"type": "http", "headers": []})
    if status is None:
        await visitor.limit(request, "test", 2, 60)
    else:
        with pytest.raises(HTTPException) as error:
            await visitor.limit(request, "test", 2, 60)
        assert error.value.status_code == status
        if status == 429:
            assert error.value.headers["Retry-After"] == "60"
    assert redis.eval.await_args.args[-2:] == (2, 60)
