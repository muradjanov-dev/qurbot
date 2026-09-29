"""Real Redis coverage for browser-bound Telegram login challenge transitions."""

from __future__ import annotations

import asyncio
import os
import re
import secrets

import pytest
from redis.asyncio import Redis

from app.core.config import settings
from app.services.bot_login import BotLoginUnavailable, open_bot_login_service


@pytest.fixture
async def bot_login_service(monkeypatch: pytest.MonkeyPatch):
    redis_url = os.environ.get("BOT_LOGIN_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("isolated Telegram login Redis not configured")
    monkeypatch.setattr(settings, "bot_token", "login-test-" + secrets.token_hex(16))
    redis = Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.ping()
    except Exception as exc:
        await redis.aclose()
        pytest.fail(f"isolated Telegram login Redis is unavailable: {exc}")
    try:
        async with open_bot_login_service(redis=redis) as service:
            yield service, redis
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_challenge_claim_approval_and_consume_are_browser_bound_and_once_only(
    bot_login_service,
) -> None:
    service, _redis = bot_login_service
    challenge = await service.create("/catalog", "Chrome on macOS")

    assert re.fullmatch(r"[A-Za-z0-9_-]{32}", challenge.token)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge.browser_secret)
    assert re.fullmatch(r"\d{6}", challenge.code)
    assert challenge.expires_in == 300
    assert await service.browser_status(challenge.token, "wrong-secret") is None

    state = await service.browser_status(challenge.token, challenge.browser_secret)
    assert state is not None
    assert (state.status, state.code, state.browser_label, state.next_path) == (
        "pending",
        challenge.code,
        "Chrome on macOS",
        "/catalog",
    )
    assert state.tg_id is None
    assert 0 < state.expires_in <= 300

    claimed = await service.claim(challenge.token, 123456)
    assert claimed is not None and claimed.status == "claimed" and claimed.tg_id == 123456
    retry = await service.claim(challenge.token, 123456)
    assert retry is not None and retry.status == claimed.status and retry.tg_id == claimed.tg_id
    assert retry.expires_in <= claimed.expires_in
    assert await service.claim(challenge.token, 654321) is None
    assert await service.decide(challenge.token, 654321, approve=True) is False
    assert await service.decide(challenge.token, 123456, approve=True) is True
    assert await service.decide(challenge.token, 123456, approve=False) is False

    approved = await service.browser_status(challenge.token, challenge.browser_secret)
    assert approved is not None and approved.status == "approved"
    assert await service.consume(challenge.token, "wrong-secret") is None
    results = await asyncio.gather(
        service.consume(challenge.token, challenge.browser_secret),
        service.consume(challenge.token, challenge.browser_secret),
    )
    assert sorted(result for result in results if result is not None) == [123456]
    assert results.count(None) == 1
    assert await service.browser_status(challenge.token, challenge.browser_secret) is None


@pytest.mark.asyncio
async def test_denied_and_cancelled_challenges_cannot_be_consumed(bot_login_service) -> None:
    service, _redis = bot_login_service
    denied = await service.create("/account", "Firefox")
    assert await service.claim(denied.token, 222) is not None
    assert await service.decide(denied.token, 222, approve=False) is True
    denied_state = await service.browser_status(denied.token, denied.browser_secret)
    assert denied_state is not None and denied_state.status == "denied"
    assert await service.consume(denied.token, denied.browser_secret) is None

    cancelled = await service.create("/catalog", "Safari")
    assert await service.cancel(cancelled.token, "wrong-secret") is False
    assert await service.cancel(cancelled.token, cancelled.browser_secret) is True
    assert await service.cancel(cancelled.token, cancelled.browser_secret) is False
    assert await service.browser_status(cancelled.token, cancelled.browser_secret) is None


@pytest.mark.asyncio
async def test_claim_race_binds_exactly_one_telegram_account(bot_login_service) -> None:
    service, _redis = bot_login_service
    challenge = await service.create("/", "Chrome")

    claims = await asyncio.gather(
        service.claim(challenge.token, 111),
        service.claim(challenge.token, 222),
    )

    assert sum(claim is not None for claim in claims) == 1
    assert await service.cancel(challenge.token, challenge.browser_secret) is True


@pytest.mark.asyncio
async def test_browser_secret_and_token_shape_are_validated_before_redis(bot_login_service) -> None:
    service, redis = bot_login_service
    challenge = await service.create("/", "Chrome")
    before = await redis.dbsize()

    assert await service.browser_status("not-a-token", challenge.browser_secret) is None
    assert await service.browser_status(challenge.token, "short") is None
    assert await service.claim("not-a-token", 123) is None
    assert await service.decide("not-a-token", 123, approve=True) is False
    assert await service.consume("not-a-token", challenge.browser_secret) is None
    assert await service.cancel("not-a-token", challenge.browser_secret) is False
    assert await redis.dbsize() == before
    assert await service.cancel(challenge.token, challenge.browser_secret) is True


@pytest.mark.asyncio
async def test_redis_failures_are_reported_as_unavailable_and_never_approved() -> None:
    class OfflineRedis:
        async def set(self, *_args, **_kwargs):
            raise ConnectionError("offline")

        async def eval(self, *_args, **_kwargs):
            raise TimeoutError("timed out")

    async with open_bot_login_service(redis=OfflineRedis()) as service:  # type: ignore[arg-type]
        with pytest.raises(BotLoginUnavailable):
            await service.create("/", "Chrome")
        with pytest.raises(BotLoginUnavailable):
            await service.browser_status("A" * 32, "B" * 43)


@pytest.mark.asyncio
async def test_unsafe_next_path_is_rejected_before_redis(bot_login_service) -> None:
    service, redis = bot_login_service
    before = await redis.dbsize()

    with pytest.raises(ValueError, match="invalid_next_path"):
        await service.create("//attacker.example", "Chrome")

    assert await redis.dbsize() == before
