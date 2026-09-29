"""HTTP security and session attachment for browser Telegram login."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.services.bot_login import BotLoginUnavailable, CreatedChallenge, State
from app.web.storefront.routers import auth
from app.web.storefront.session import GUEST_COOKIE, SESSION_COOKIE, read_session
from tests.integration.test_storefront_web import _seed, _sign_in_admin
from tests.integration.test_storefront_web import client as storefront_client


class MemoryBotLoginService:
    def __init__(self) -> None:
        self.states: dict[str, State] = {}
        self.secrets: dict[str, str] = {}
        self.create_calls = 0
        self.consume_calls = 0
        self.cancel_calls = 0

    async def create(self, next_path: str, browser_label: str) -> CreatedChallenge:
        self.create_calls += 1
        token = f"{self.create_calls:032d}"
        secret = "s" * 43
        code = f"{self.create_calls:06d}"
        self.secrets[token] = secret
        self.states[token] = State(
            status="pending",
            code=code,
            browser_label=browser_label,
            next_path=next_path,
            tg_id=None,
            expires_in=300,
        )
        return CreatedChallenge(token, secret, code, 300)

    async def browser_status(self, token: str, secret: str) -> State | None:
        if self.secrets.get(token) != secret:
            return None
        return self.states.get(token)

    async def claim(self, token: str, tg_id: int) -> State | None:
        state = self.states.get(token)
        if state is None or state.status != "pending":
            return None
        claimed = State(
            status="claimed",
            code=state.code,
            browser_label=state.browser_label,
            next_path=state.next_path,
            tg_id=tg_id,
            expires_in=state.expires_in,
        )
        self.states[token] = claimed
        return claimed

    async def decide(self, token: str, tg_id: int, approve: bool) -> bool:
        state = self.states.get(token)
        if state is None or state.status != "claimed" or state.tg_id != tg_id:
            return False
        self.states[token] = State(
            status="approved" if approve else "denied",
            code=state.code,
            browser_label=state.browser_label,
            next_path=state.next_path,
            tg_id=state.tg_id,
            expires_in=state.expires_in,
        )
        return True

    async def consume(self, token: str, secret: str) -> int | None:
        state = self.states.get(token)
        if (
            self.secrets.get(token) != secret
            or state is None
            or state.status != "approved"
            or state.tg_id is None
        ):
            return None
        self.consume_calls += 1
        del self.states[token]
        del self.secrets[token]
        return state.tg_id

    async def cancel(self, token: str, secret: str) -> bool:
        if self.secrets.get(token) != secret:
            return False
        self.cancel_calls += 1
        self.states.pop(token, None)
        self.secrets.pop(token, None)
        return True


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)  # type: ignore[attr-defined]


@pytest.fixture
def bot_login_service(monkeypatch: pytest.MonkeyPatch) -> MemoryBotLoginService:
    service = MemoryBotLoginService()

    @asynccontextmanager
    async def open_service() -> AsyncIterator[MemoryBotLoginService]:
        yield service

    async def allow_rate_limit(_request: Any, _bucket: str, _maximum: int, _seconds: int) -> None:
        return None

    monkeypatch.setattr(auth, "open_bot_login_service", open_service)
    monkeypatch.setattr(auth, "limit", allow_rate_limit)
    monkeypatch.setattr(settings, "telegram_login_bot_username", "TezqurBot")
    return service


def _headers(*, bot_header: bool = True, origin: str = "http://testserver") -> dict[str, str]:
    headers = {
        "Origin": origin,
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Chrome/124 Windows",
    }
    if bot_header:
        headers["X-Bot-Login"] = "1"
    return headers


def _start(client: TestClient, next_path: str = "/checkout") -> Any:
    return client.post(
        "/auth/bot/start",
        json={"next": next_path},
        headers=_headers(),
    )


def test_bot_login_feature_is_disabled_without_a_valid_bot_username(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_login_bot_username", "not valid")
    page = client.get("/login")
    assert page.status_code == 200
    assert 'data-bot-login-enabled="0"' in page.text
    unavailable = client.post("/auth/bot/start", json={"next": "/account"}, headers=_headers())
    assert unavailable.status_code == 503


@pytest.mark.asyncio
async def test_start_checks_origin_rate_limits_and_reuses_browser_cookie(
    client: TestClient,
    bot_login_service: MemoryBotLoginService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits: list[tuple[str, int, int]] = []

    async def fake_limit(_request: Any, bucket: str, maximum: int, seconds: int) -> None:
        limits.append((bucket, maximum, seconds))

    monkeypatch.setattr(auth, "limit", fake_limit)

    missing_header = client.post(
        "/auth/bot/start", json={"next": "/checkout"}, headers=_headers(bot_header=False)
    )
    assert missing_header.status_code == 403
    cross_origin = client.post(
        "/auth/bot/start",
        json={"next": "/checkout"},
        headers=_headers(origin="https://attacker.invalid"),
    )
    assert cross_origin.status_code == 403
    oversized_next = client.post(
        "/auth/bot/start",
        json={"next": "/" + "x" * 2048},
        headers=_headers(),
    )
    assert oversized_next.status_code == 422

    started = _start(client)
    assert started.status_code == 200
    payload = started.json()
    assert set(payload) == {"ok", "bot_url", "code", "expires_in"}
    assert payload["ok"] is True
    assert payload["bot_url"].startswith("https://t.me/TezqurBot?start=login_")
    assert payload["expires_in"] == 300
    assert "s" * 43 not in started.text
    cookie = client.cookies.get("qb_bot_login")
    assert cookie is not None and len(cookie.split(".", 1)[1]) == 43
    set_cookie = next(
        value for key, value in started.headers.multi_items() if key.lower() == "set-cookie"
    )
    assert "httponly" in set_cookie.lower()
    assert (
        bot_login_service.states[next(iter(bot_login_service.states))].browser_label
        == "Chrome on Windows"
    )
    assert len(limits) == 1 and limits[0][1:] == (10, 600)

    retried = _start(client, "/manage")
    assert retried.status_code == 200
    assert retried.json()["code"] == payload["code"]
    assert bot_login_service.create_calls == 1
    assert len(limits) == 1

    status = client.get("/auth/bot/status")
    assert status.status_code == 200
    assert set(status.json()) == {"status", "expires_in"}
    assert status.json()["status"] == "pending"
    assert "tg_id" not in status.text and "browser_secret" not in status.text


@pytest.mark.asyncio
async def test_complete_is_browser_bound_once_only_and_uses_existing_user_role(
    client: TestClient,
    test_session: AsyncSession,
    bot_login_service: MemoryBotLoginService,
) -> None:
    fixture = await _seed(test_session)
    user = await test_session.get(User, fixture.user_id)
    assert user is not None and user.tg_id is not None
    client.cookies.set(GUEST_COOKIE, "g" * 43)
    started = _start(client)
    assert started.status_code == 200
    token = started.json()["bot_url"].split("login_", 1)[1]
    assert await bot_login_service.claim(token, user.tg_id) is not None
    assert await bot_login_service.decide(token, user.tg_id, approve=True)

    other_browser = TestClient(client.app)
    try:
        cross_browser = other_browser.post("/auth/bot/complete", headers=_headers())
    finally:
        other_browser.close()
    assert cross_browser.status_code == 410
    assert bot_login_service.consume_calls == 0

    approved_status = client.get("/auth/bot/status")
    assert approved_status.json() == {"status": "approved", "expires_in": 300}
    completed = client.post("/auth/bot/complete", headers=_headers())
    assert completed.status_code == 200
    assert completed.json() == {"ok": True, "redirect": "/checkout"}
    signed = read_session(client.cookies.get(SESSION_COOKIE))
    assert signed is not None and signed.tg_id == user.tg_id and signed.user_id == user.id
    assert client.cookies.get(GUEST_COOKIE) == "g" * 43
    assert bot_login_service.consume_calls == 1

    replay = client.post("/auth/bot/complete", headers=_headers())
    assert replay.status_code == 410
    assert bot_login_service.consume_calls == 1

    admin = await _sign_in_admin(client, test_session)
    assert admin.tg_id is not None
    second = _start(client, "/account")
    token2 = second.json()["bot_url"].split("login_", 1)[1]
    assert await bot_login_service.claim(token2, admin.tg_id)
    assert await bot_login_service.decide(token2, admin.tg_id, approve=True)
    admin_result = client.post("/auth/bot/complete", headers=_headers())
    assert admin_result.status_code == 200
    assert admin_result.json() == {"ok": True, "redirect": "/manage"}

    explicit = _start(client, "/checkout")
    token3 = explicit.json()["bot_url"].split("login_", 1)[1]
    assert await bot_login_service.claim(token3, admin.tg_id)
    assert await bot_login_service.decide(token3, admin.tg_id, approve=True)
    explicit_result = client.post("/auth/bot/complete", headers=_headers())
    assert explicit_result.status_code == 200
    assert explicit_result.json() == {"ok": True, "redirect": "/checkout"}


@pytest.mark.asyncio
async def test_blocked_and_revoked_challenges_never_attach_session(
    client: TestClient,
    test_session: AsyncSession,
    bot_login_service: MemoryBotLoginService,
) -> None:
    blocked_user = User(tg_id=998877665, full_name="Blocked", is_blocked=True)
    test_session.add(blocked_user)
    await test_session.flush()
    assert blocked_user.tg_id is not None
    blocked_start = _start(client, "/account")
    assert blocked_start.status_code == 200, blocked_start.text
    blocked_token = blocked_start.json()["bot_url"].split("login_", 1)[1]
    assert await bot_login_service.claim(blocked_token, blocked_user.tg_id)
    assert await bot_login_service.decide(blocked_token, blocked_user.tg_id, approve=True)

    blocked = client.post("/auth/bot/complete", headers=_headers())
    assert blocked.status_code == 403
    assert blocked.json()["blocked"] is True
    assert bot_login_service.consume_calls == 0
    assert client.cookies.get(SESSION_COOKIE) is None

    revoked_start = _start(client, "/catalog")
    revoked_token = revoked_start.json()["bot_url"].split("login_", 1)[1]
    cancelled = client.post("/auth/bot/cancel", headers=_headers())
    assert cancelled.status_code == 200 and cancelled.json() == {"ok": True}
    assert client.get("/auth/bot/status").json() == {"status": "expired", "expires_in": 0}
    revoked_complete = client.post("/auth/bot/complete", headers=_headers())
    assert revoked_complete.status_code == 410
    assert revoked_token not in revoked_complete.text


def test_logout_clears_pending_login_cookie_without_redis(
    client: TestClient,
    bot_login_service: MemoryBotLoginService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = _start(client)
    token = started.json()["bot_url"].split("login_", 1)[1]
    assert client.cookies.get("qb_bot_login") is not None

    @asynccontextmanager
    async def unavailable_service() -> AsyncIterator[MemoryBotLoginService]:
        raise BotLoginUnavailable()
        yield bot_login_service

    monkeypatch.setattr(auth, "open_bot_login_service", unavailable_service)
    logged_out = client.post("/logout", follow_redirects=False)
    assert logged_out.status_code == 303
    assert client.cookies.get("qb_bot_login") is None
    assert token in bot_login_service.states
    complete = client.post("/auth/bot/complete", headers=_headers())
    assert complete.status_code == 410
