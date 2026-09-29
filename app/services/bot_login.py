"""Short-lived, browser-bound challenges for Telegram account sign-in."""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, cast

from redis.asyncio import Redis

from app.core.config import settings

_CHALLENGE_TTL_SECONDS = 300
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32}$")
_BROWSER_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_LOGIN_NAMESPACE = "bot-login"

_BROWSER_STATUS = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local state = cjson.decode(raw)
if state.browser_secret_hash ~= ARGV[1] then return nil end
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then return nil end
return {raw, tostring(ttl)}
"""

_CLAIM = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local state = cjson.decode(raw)
local claimant = ARGV[1]
if state.tg_id ~= cjson.null and state.tg_id ~= nil then
  if tostring(state.tg_id) == claimant then
    local ttl = redis.call('PTTL', KEYS[1])
    if ttl <= 0 then return nil end
    return {raw, tostring(ttl)}
  end
  return nil
end
if state.status ~= 'pending' then return nil end
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then return nil end
state.status = 'claimed'
state.tg_id = claimant
local updated = cjson.encode(state)
redis.call('SET', KEYS[1], updated, 'PX', ttl)
return {updated, tostring(ttl)}
"""

_DECIDE = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
if tostring(state.tg_id or '') ~= ARGV[1] then return 0 end
local desired = ARGV[2]
if state.status == desired then return 1 end
if state.status ~= 'claimed' then return 0 end
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then return 0 end
state.status = desired
local updated = cjson.encode(state)
redis.call('SET', KEYS[1], updated, 'PX', ttl)
return 1
"""

_CONSUME = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local state = cjson.decode(raw)
if state.browser_secret_hash ~= ARGV[1] or state.status ~= 'approved' then return nil end
local tg_id = state.tg_id
if not tg_id then return nil end
redis.call('DEL', KEYS[1])
return tostring(tg_id)
"""

_CANCEL = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
if state.browser_secret_hash ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
return 1
"""

LoginStatus = Literal["pending", "claimed", "approved", "denied"]


@dataclass(frozen=True, slots=True)
class CreatedChallenge:
    token: str
    browser_secret: str
    code: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class State:
    status: LoginStatus
    code: str
    browser_label: str
    next_path: str
    tg_id: int | None
    expires_in: int


class BotLoginUnavailable(RuntimeError):
    """Redis is unavailable; browser login must fail closed."""

    def __init__(self) -> None:
        super().__init__("bot_login_unavailable")


class BotLoginService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._namespace = hashlib.sha256(settings.bot_token.encode()).hexdigest()

    async def create(self, next_path: str, browser_label: str) -> CreatedChallenge:
        safe_path = _validated_next_path(next_path)
        label = _validated_browser_label(browser_label)
        browser_secret = secrets.token_urlsafe(32)
        browser_secret_hash = _secret_hash(browser_secret)

        for _ in range(3):
            token = secrets.token_urlsafe(24)
            key = self._key(token)
            code = f"{secrets.randbelow(1_000_000):06d}"
            state = {
                "status": "pending",
                "code": code,
                "browser_label": label,
                "next_path": safe_path,
                "tg_id": None,
                "expires_in": _CHALLENGE_TTL_SECONDS,
                "browser_secret_hash": browser_secret_hash,
            }
            try:
                created = await self._redis.set(
                    key,
                    json.dumps(state, separators=(",", ":")),
                    ex=_CHALLENGE_TTL_SECONDS,
                    nx=True,
                )
            except Exception as exc:
                raise BotLoginUnavailable() from exc
            if created:
                return CreatedChallenge(
                    token=token,
                    browser_secret=browser_secret,
                    code=code,
                    expires_in=_CHALLENGE_TTL_SECONDS,
                )
        raise BotLoginUnavailable()

    async def browser_status(self, token: str, secret: str) -> State | None:
        key = self._key_or_none(token)
        secret_hash = _secret_hash_or_none(secret)
        if key is None or secret_hash is None:
            return None
        reply = await self._eval(_BROWSER_STATUS, key, secret_hash)
        return _state_from_reply(reply)

    async def claim(self, token: str, tg_id: int) -> State | None:
        key = self._key_or_none(token)
        if key is None or not _valid_tg_id(tg_id):
            return None
        reply = await self._eval(_CLAIM, key, str(tg_id))
        return _state_from_reply(reply)

    async def decide(self, token: str, tg_id: int, approve: bool) -> bool:
        key = self._key_or_none(token)
        if key is None or not _valid_tg_id(tg_id):
            return False
        desired = "approved" if approve else "denied"
        result = await self._eval(_DECIDE, key, str(tg_id), desired)
        return bool(result)

    async def consume(self, token: str, secret: str) -> int | None:
        key = self._key_or_none(token)
        secret_hash = _secret_hash_or_none(secret)
        if key is None or secret_hash is None:
            return None
        result = await self._eval(_CONSUME, key, secret_hash)
        if result is None:
            return None
        try:
            value = _text(result)
            return int(value) if value.isdigit() and int(value) > 0 else None
        except (TypeError, ValueError) as exc:
            raise BotLoginUnavailable() from exc

    async def cancel(self, token: str, secret: str) -> bool:
        key = self._key_or_none(token)
        secret_hash = _secret_hash_or_none(secret)
        if key is None or secret_hash is None:
            return False
        return bool(await self._eval(_CANCEL, key, secret_hash))

    def _key(self, token: str) -> str:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return f"{_LOGIN_NAMESPACE}:{self._namespace}:{token_hash}"

    def _key_or_none(self, token: str) -> str | None:
        if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
            return None
        return self._key(token)

    async def _eval(self, script: str, key: str, *args: str) -> object:
        try:
            result = cast(Awaitable[object], self._redis.eval(script, 1, key, *args))
            return await result
        except Exception as exc:
            raise BotLoginUnavailable() from exc


@asynccontextmanager
async def open_bot_login_service(redis: Redis | None = None) -> AsyncIterator[BotLoginService]:
    """Open the bounded Redis client used for one browser-login request."""
    if redis is not None:
        yield BotLoginService(redis)
        return
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
        )
    except Exception as exc:
        raise BotLoginUnavailable() from exc
    try:
        yield BotLoginService(client)
    finally:
        try:
            await client.aclose()
        except Exception as exc:
            raise BotLoginUnavailable() from exc


def _validated_next_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or len(value) > 2048
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("invalid_next_path")
    return value


def _validated_browser_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_browser_label")
    label = " ".join(value.split())
    if not label or len(label) > 120 or any(ord(char) < 32 for char in label):
        raise ValueError("invalid_browser_label")
    return label


def _valid_tg_id(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _secret_hash_or_none(secret: str) -> str | None:
    if not isinstance(secret, str) or _BROWSER_SECRET_PATTERN.fullmatch(secret) is None:
        return None
    return _secret_hash(secret)


def _state_from_reply(reply: object) -> State | None:
    if not isinstance(reply, list | tuple) or len(reply) != 2:
        return None
    try:
        raw = json.loads(_text(reply[0]))
        if not isinstance(raw, dict):
            raise BotLoginUnavailable()
        ttl_ms = int(_text(reply[1]))
        if ttl_ms <= 0 or raw.get("status") not in {"pending", "claimed", "approved", "denied"}:
            return None
        tg_id_raw = raw.get("tg_id")
        return State(
            status=raw["status"],
            code=str(raw["code"]),
            browser_label=str(raw["browser_label"]),
            next_path=str(raw["next_path"]),
            tg_id=int(tg_id_raw) if tg_id_raw is not None else None,
            expires_in=max(1, math.ceil(ttl_ms / 1000)),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BotLoginUnavailable() from exc


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, str):
        return value
    raise TypeError("unexpected_redis_reply")
