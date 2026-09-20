"""A signed Telegram launch identifies the existing account, never its claimed role."""

import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db_session
from app.main import create_app
from app.web.storefront.session import SESSION_COOKIE, read_session
from tests.unit.test_web_auth import BOT_TOKEN, _init_data


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [("admin", 200), ("customer", 403)])
async def test_signed_launch_preserves_database_role(test_session, monkeypatch, role, expected):
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "admin_tg_ids", [])
    user = User(tg_id=555, role=role, full_name="Login fixture")
    test_session.add(user)
    await test_session.flush()
    app = create_app()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[get_db_session] = session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.example"
    ) as client:
        # Even a correctly signed payload cannot upgrade the DB role.
        proof = _init_data(user=json.dumps({"id": 555, "first_name": "Test", "role": "admin"}))
        response = await client.post("/auth/webapp", json={"init_data": proof, "next": "/chat"})
        assert response.status_code == 200
        assert response.json()["redirect"] == "/chat"
        cookie_header = response.headers["set-cookie"].lower()
        for attribute in ("httponly", "secure", "samesite=none", "partitioned", "path=/"):
            assert attribute in cookie_header
        signed = read_session(client.cookies.get(SESSION_COOKIE))
        assert signed and signed.user_id == user.id
        assert (await client.get("/api/cart")).status_code == 200
        assert (await client.get("/api/chat/operator")).status_code == expected
        assert user.role == role
        assert (await client.get("/login?next=/chat")).headers["location"] == "/chat"
        # SameSite=None must not permit cross-site form writes or logout.
        for path in ("/logout", "/account/addresses", "/auth/webapp"):
            denied = await client.post(path, headers={"Origin": "https://attacker.example"})
            assert denied.status_code == 403
        assert (await client.get("/api/cart")).status_code == 200
        assert (await client.post("/api/chat/handoff", json={})).status_code == 403
        logout = await client.post("/logout", headers={"Origin": "https://shop.example"})
        assert logout.status_code == 303
        assert len(logout.headers.get_list("set-cookie")) == 4
        assert (await client.get("/api/cart")).status_code == 401


@pytest.mark.asyncio
async def test_empty_or_forged_launch_cannot_get_session(test_session, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", BOT_TOKEN)
    app = create_app()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[get_db_session] = session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.example"
    ) as client:
        for proof in ("", _init_data() + "&user=%7B%22id%22%3A999%7D"):
            response = await client.post("/auth/webapp", json={"init_data": proof})
            assert response.status_code == 401
            assert SESSION_COOKIE not in client.cookies
