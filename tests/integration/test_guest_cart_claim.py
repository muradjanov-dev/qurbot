"""A verified Telegram login can claim only its browser's guest cart."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from test_sales_postgres import pg_sessions as _pg_sessions

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.user import User, VisitorSession
from app.db.session import get_db_session
from app.main import create_app
from app.services.cart_service import CartService, InvalidCartItem
from app.services.guest_cart_claim_service import (
    claim_guest_cart,
    resolve_guest_cart_claim,
)
from app.web.storefront.security import csrf_token
from app.web.storefront.session import GUEST_COOKIE, SESSION_COOKIE, sign_session
from tests.unit.test_web_auth import BOT_TOKEN, _init_data

pg_sessions = _pg_sessions


async def _fixture(session: AsyncSession) -> tuple[User, User, CanonicalProduct]:
    category = Category(slug="guest-claim", name_uz="Test", name_ru="Test")
    target = User(tg_id=72001, full_name="Telegram user")
    guest = User(tg_id=None, full_name="Visitor", referral_source="guest_web")
    session.add_all(
        [
            category,
            target,
            guest,
            Unit(code="dona", name_uz="Dona", name_ru="Штука", dimension="count"),
        ]
    )
    await session.flush()
    product = CanonicalProduct(
        slug="guest-claim-item",
        name_uz="Test item",
        name_uz_cyrl="Тест",
        name_ru="Тест",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="test",
    )
    session.add(product)
    await session.flush()
    return target, guest, product


def _visitor(token: str, guest_id: int, *, expires_at: datetime | None = None) -> VisitorSession:
    return VisitorSession(
        token_hash=sha256(token.encode()).hexdigest(),
        user_id=guest_id,
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_claim_merges_duplicate_quantity_by_max_and_consumes_guest_session(test_session):
    target, guest, product = await _fixture(test_session)
    token = "v" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "7", expected_revision=0, unit_code="dona"
    )

    result = await claim_guest_cart(test_session, target, token)
    assert result.status == "claimed"
    target_cart = await CartService(test_session).get(target.id)
    guest_cart = await CartService(test_session).get(guest.id)
    assert [(line["qty"], line["unit_code"]) for line in target_cart.lines] == [("7", "dona")]
    assert guest_cart.lines == ()
    assert await test_session.get(VisitorSession, sha256(token.encode()).hexdigest()) is None

    # A second request with the same browser cookie cannot apply the quantity
    # again because the visitor session was consumed in the claim transaction.
    replay = await claim_guest_cart(test_session, target, token)
    assert replay.status == "none"
    assert (await CartService(test_session).get(target.id)).lines[0]["qty"] == "7"


@pytest.mark.asyncio
async def test_conflicting_units_keep_both_carts_and_require_review(test_session):
    target, guest, product = await _fixture(test_session)
    token = "c" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "2", expected_revision=0, unit_code="qop"
    )

    result = await claim_guest_cart(test_session, target, token)
    assert result.needs_review and result.reason == "unit_conflict"
    source = await CartService(test_session).get(guest.id)
    destination = await CartService(test_session).get(target.id)
    assert [(line["qty"], line["unit_code"]) for line in source.lines] == [("5", "dona")]
    assert [(line["qty"], line["unit_code"]) for line in destination.lines] == [("2", "qop")]
    assert await test_session.get(VisitorSession, sha256(token.encode()).hexdigest()) is not None


@pytest.mark.asyncio
async def test_resolution_can_drop_selected_guest_lines_only_when_claim_succeeds(test_session):
    target, guest, product = await _fixture(test_session)
    token = "d" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "2", expected_revision=0, unit_code="qop"
    )

    invalid = await resolve_guest_cart_claim(
        test_session, target, token, drop_guest_ids=[product.id + 1]
    )
    assert invalid.status == "invalid_selection"
    assert (await CartService(test_session).get(guest.id)).lines[0]["qty"] == "5"
    assert (await CartService(test_session).get(target.id)).lines[0]["unit_code"] == "qop"

    result = await resolve_guest_cart_claim(
        test_session, target, token, drop_guest_ids=[product.id]
    )
    assert result.status == "claimed"
    assert (await CartService(test_session).get(guest.id)).lines == ()
    assert (await CartService(test_session).get(target.id)).lines[0]["unit_code"] == "qop"
    assert await test_session.get(VisitorSession, sha256(token.encode()).hexdigest()) is None


@pytest.mark.asyncio
async def test_resolution_can_remove_account_line_and_merge_guest_line(test_session):
    target, guest, product = await _fixture(test_session)
    token = "a" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "2", expected_revision=0, unit_code="qop"
    )

    result = await resolve_guest_cart_claim(
        test_session, target, token, remove_account_ids=[product.id]
    )
    assert result.status == "claimed"
    assert [
        (line["qty"], line["unit_code"])
        for line in (await CartService(test_session).get(target.id)).lines
    ] == [("5", "dona")]
    assert (await CartService(test_session).get(guest.id)).lines == ()


@pytest.mark.asyncio
async def test_failed_resolution_keeps_both_carts_and_guest_cookie_claimable(test_session):
    target, guest, product = await _fixture(test_session)
    category = await test_session.get(Category, product.category_id)
    assert category is not None
    extra = CanonicalProduct(
        slug="guest-claim-extra",
        name_uz="Extra",
        name_uz_cyrl="Экстра",
        name_ru="Extra",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="extra",
    )
    test_session.add(extra)
    await test_session.flush()
    token = "f" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        guest.id, extra.id, "3", expected_revision=1, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "2", expected_revision=0, unit_code="qop"
    )

    result = await resolve_guest_cart_claim(
        test_session,
        target,
        token,
        drop_guest_ids=[extra.id],
    )
    assert result.needs_review and result.reason == "unit_conflict"
    source_lines = (await CartService(test_session).get(guest.id)).lines
    assert {(line["canonical_id"], line["qty"]) for line in source_lines} == {
        (product.id, "5"),
        (extra.id, "3"),
    }
    assert (await CartService(test_session).get(target.id)).lines[0]["unit_code"] == "qop"
    assert await test_session.get(VisitorSession, sha256(token.encode()).hexdigest()) is not None


@pytest.mark.asyncio
async def test_expired_or_unrelated_guest_token_cannot_claim_a_cart(test_session):
    target, guest, product = await _fixture(test_session)
    expired = "e" * 43
    test_session.add(
        _visitor(expired, guest.id, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )

    assert (await claim_guest_cart(test_session, target, expired)).status == "none"
    assert (await claim_guest_cart(test_session, target, "x" * 43)).status == "none"
    assert (await CartService(test_session).get(guest.id)).lines[0]["qty"] == "5"
    assert (await CartService(test_session).get(target.id)).lines == ()


@pytest.mark.asyncio
async def test_webapp_login_claim_uses_browser_cookie_not_request_owner_id(
    test_session, monkeypatch
):
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "enabled_category_slugs", [])
    target, guest, product = await _fixture(test_session)
    unrelated = User(tg_id=None, full_name="Other browser")
    test_session.add(unrelated)
    await test_session.flush()
    token = "w" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        unrelated.id, product.id, "9", expected_revision=0, unit_code="dona"
    )
    await test_session.commit()
    app = create_app()

    async def session_override():
        yield test_session

    app.dependency_overrides[get_db_session] = session_override
    proof = _init_data(user=json.dumps({"id": target.tg_id, "first_name": "Telegram user"}))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.example"
    ) as client:
        client.cookies.set(GUEST_COOKIE, token)
        response = await client.post(
            "/auth/webapp",
            json={
                "init_data": proof,
                "next": "/checkout",
                "guest_user_id": unrelated.id,
            },
        )
        assert response.status_code == 200
        assert response.json()["redirect"] == "/checkout"
        assert (await CartService(test_session).get(target.id)).lines[0]["qty"] == "5"
        assert (await CartService(test_session).get(guest.id)).lines == ()
        assert (await CartService(test_session).get(unrelated.id)).lines[0]["qty"] == "9"
        assert await test_session.get(VisitorSession, sha256(token.encode()).hexdigest()) is None
        assert "qb_visitor=" in "\n".join(response.headers.get_list("set-cookie"))


@pytest.mark.asyncio
async def test_claim_retry_is_csrf_protected_and_keeps_both_carts_until_resolved(
    test_session,
):
    target, guest, product = await _fixture(test_session)
    token = "m" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "2", expected_revision=0, unit_code="qop"
    )
    await test_session.commit()
    app = create_app()

    async def session_override():
        yield test_session

    app.dependency_overrides[get_db_session] = session_override
    session_cookie = sign_session(user_id=target.id, tg_id=target.tg_id)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.example"
    ) as client:
        client.cookies.set(SESSION_COOKIE, session_cookie)
        client.cookies.set(GUEST_COOKIE, token)
        denied = await client.post("/api/cart/claim-guest")
        assert denied.status_code == 403
        assert (await CartService(test_session).get(guest.id)).lines[0]["qty"] == "5"

        cookie_header = (f"{SESSION_COOKIE}={session_cookie}; {GUEST_COOKIE}={token}").encode()
        request = Request({"type": "http", "headers": [(b"cookie", cookie_header)]})
        headers = {"X-CSRF-Token": csrf_token(request), "Origin": "https://shop.example"}
        conflict = await client.post("/api/cart/claim-guest", headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "guest_cart_review_required"
        assert (await CartService(test_session).get(target.id)).lines[0]["unit_code"] == "qop"
        assert (await CartService(test_session).get(guest.id)).lines[0]["unit_code"] == "dona"

        preview = await client.get("/api/cart/claim-guest")
        assert preview.status_code == 200
        assert preview.json()["source_lines"] == [
            {
                "canonical_id": product.id,
                "qty": "5",
                "unit_code": "dona",
                "name": "Тест",
                "requires_confirmation": True,
            }
        ]

        removed = await client.delete(
            f"/api/cart/items/{product.id}?expected_revision=1", headers=headers
        )
        assert removed.status_code == 200
        claimed = await client.post("/api/cart/claim-guest", headers=headers)
        assert claimed.status_code == 200 and claimed.json()["status"] == "claimed"
        assert (await CartService(test_session).get(target.id)).lines[0]["qty"] == "5"
        assert (await CartService(test_session).get(guest.id)).lines == ()
        assert "qb_visitor=" in "\n".join(claimed.headers.get_list("set-cookie"))


@pytest.mark.asyncio
async def test_guest_cart_preview_is_bound_to_the_presented_cookie(test_session):
    target, guest, product = await _fixture(test_session)
    unrelated_guest = User(tg_id=None, full_name="Another visitor")
    test_session.add(unrelated_guest)
    await test_session.flush()
    token = "p" * 43
    unrelated_token = "u" * 43
    test_session.add_all([_visitor(token, guest.id), _visitor(unrelated_token, unrelated_guest.id)])
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        unrelated_guest.id, product.id, "9", expected_revision=0, unit_code="dona"
    )
    await test_session.commit()
    app = create_app()

    async def session_override():
        yield test_session

    app.dependency_overrides[get_db_session] = session_override
    session_cookie = sign_session(user_id=target.id, tg_id=target.tg_id)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.example"
    ) as client:
        client.cookies.set(SESSION_COOKIE, session_cookie)
        client.cookies.set(GUEST_COOKIE, token)
        preview = await client.get("/api/cart/claim-guest")
        assert preview.status_code == 200
        assert preview.json()["source_lines"][0]["qty"] == "5"

        client.cookies.set(GUEST_COOKIE, unrelated_token)
        unrelated_preview = await client.get("/api/cart/claim-guest")
        assert unrelated_preview.status_code == 200
        assert unrelated_preview.json()["status"] == "review_required"
        assert unrelated_preview.json()["source_lines"][0]["qty"] == "9"


@pytest.mark.asyncio
async def test_claim_api_rolls_back_account_removal_if_merge_fails(test_session, monkeypatch):
    target, guest, product = await _fixture(test_session)
    target_id, guest_id, product_id = target.id, guest.id, product.id
    token = "z" * 43
    test_session.add(_visitor(token, guest.id))
    await test_session.flush()
    await CartService(test_session).set_item(
        guest.id, product.id, "5", expected_revision=0, unit_code="dona"
    )
    await CartService(test_session).set_item(
        target.id, product.id, "2", expected_revision=0, unit_code="qop"
    )
    await test_session.commit()
    app = create_app()

    async def session_override():
        yield test_session

    app.dependency_overrides[get_db_session] = session_override
    session_cookie = sign_session(user_id=target_id, tg_id=target.tg_id)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.example"
    ) as client:
        client.cookies.set(SESSION_COOKIE, session_cookie)
        client.cookies.set(GUEST_COOKIE, token)
        cookie_header = (f"{SESSION_COOKIE}={session_cookie}; {GUEST_COOKIE}={token}").encode()
        request = Request({"type": "http", "headers": [(b"cookie", cookie_header)]})
        headers = {
            "X-CSRF-Token": csrf_token(request),
            "Origin": "https://shop.example",
        }

        async def fail_merge(self, user_id, lines, *, merge_key, expected_revision):
            raise InvalidCartItem("unit_conflict")

        monkeypatch.setattr(CartService, "merge", fail_merge)
        response = await client.post(
            "/api/cart/claim-guest",
            json={"remove_account_ids": [product_id]},
            headers=headers,
        )
        assert response.status_code == 409
        assert (await CartService(test_session).get(target_id)).lines[0]["unit_code"] == "qop"
        assert (await CartService(test_session).get(guest_id)).lines[0]["unit_code"] == "dona"
        assert (
            await test_session.get(VisitorSession, sha256(token.encode()).hexdigest()) is not None
        )


@pytest.mark.asyncio
async def test_postgres_concurrent_claim_consumes_guest_cart_once(pg_sessions):
    """Real row locks ensure two login callbacks cannot double-merge a cart."""
    from test_sales_postgres import seed

    target_id, product_id, _ = await seed(pg_sessions)
    token = "r" * 43
    async with pg_sessions() as session:
        guest = User(tg_id=None, full_name="Concurrent visitor")
        session.add(guest)
        await session.flush()
        session.add(_visitor(token, guest.id))
        await CartService(session).set_item(
            guest.id, product_id, "6", expected_revision=0, unit_code="dona"
        )
        await CartService(session).set_item(
            target_id, product_id, "4", expected_revision=0, unit_code="dona"
        )
        guest_id = guest.id
        await session.commit()

    async def claim_once() -> str:
        async with pg_sessions() as session:
            target = await session.get(User, target_id)
            assert target is not None
            result = await claim_guest_cart(session, target, token)
            await session.commit()
            return result.status

    statuses = await asyncio.gather(claim_once(), claim_once())
    assert sorted(statuses) == ["claimed", "none"]
    async with pg_sessions() as session:
        assert (await CartService(session).get(target_id)).lines[0]["qty"] == "6"
        assert (await CartService(session).get(guest_id)).lines == ()
