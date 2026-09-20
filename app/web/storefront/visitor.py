"""Anonymous customer sessions; no fabricated Telegram identities."""

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User, VisitorSession
from app.web.storefront.session import GUEST_COOKIE

_LIMIT = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
if used >= tonumber(ARGV[1]) then return 0 end
used = redis.call('INCR', KEYS[1])
if used == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return 1
"""


async def limit(request: Request, bucket: str, maximum: int, seconds: int) -> None:
    namespace = sha256(settings.bot_token.encode()).hexdigest()[:16]
    key = f"visitor:{namespace}:{sha256(bucket.encode()).hexdigest()}"
    try:
        async with Redis.from_url(settings.redis_url) as redis:
            allowed = await redis.eval(_LIMIT, 1, key, maximum, seconds)
    except Exception as exc:
        raise HTTPException(503, "temporarily_unavailable") from exc
    if not allowed:
        raise HTTPException(429, "rate_limited", headers={"Retry-After": str(seconds)})


def ip_key(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        networks = [ip_network(value) for value in settings.trusted_proxy_networks]
        if not any(ip_address(peer) in network for network in networks):
            return peer
        # Strip only trusted hops from the right, never trust the first value
        # supplied by a browser. The backend must not have a public listen port.
        for value in reversed(request.headers.get("x-forwarded-for", "").split(",")):
            address = ip_address(value.strip())
            if not any(address in network for network in networks):
                return str(address)
    except ValueError:
        pass
    return peer


async def create_visitor(session: AsyncSession, request: Request, lang: str) -> JSONResponse:
    if not settings.guest_sessions_enabled:
        raise HTTPException(503, "guest_sessions_paused")
    await limit(request, "sessions:" + ip_key(request), 20, 3600)
    user = User(tg_id=None, lang=lang, role="customer", referral_source="guest_web")
    session.add(user)
    await session.flush()
    token = secrets.token_urlsafe(32)
    session.add(
        VisitorSession(
            token_hash=sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await session.commit()
    response = JSONResponse({"ok": True, "mode": "guest"}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        GUEST_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=30 * 86400,
        secure=request.url.scheme == "https" or settings.webhook_base_url.startswith("https://"),
    )
    return response


async def limit_guest_message(request: Request, user: User) -> None:
    if user.tg_id is not None:
        return
    await limit(request, f"chat-minute:{user.id}", settings.guest_messages_per_minute, 60)
    await limit(request, f"chat-day:{user.id}", settings.guest_messages_per_day, 86400)
    await limit(request, "chat-ip:" + ip_key(request), settings.guest_ip_messages_per_hour, 3600)
