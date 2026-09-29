"""Telegram sign-in through widget proofs, Mini App data or private-bot confirmation.

Each path issues the existing signed session for a verified Telegram identity
and preserves database roles. Bot confirmation is short-lived and bound to the
browser that initiated it.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db_session
from app.services.bot_login import BotLoginUnavailable, open_bot_login_service
from app.services.guest_cart_claim_service import GuestCartClaim, claim_guest_cart
from app.services.house_shop import is_admin
from app.web.storefront.cookies import clear_session_cookie, set_session_cookie
from app.web.storefront.deps import current_lang, current_user, render, safe_next
from app.web.storefront.schemas import WebAppLoginIn
from app.web.storefront.security import require_same_origin_write
from app.web.storefront.session import GUEST_COOKIE, SESSION_COOKIE, read_session, sign_session
from app.web.storefront.telegram_auth import (
    TelegramIdentity,
    verify_webapp_init_data,
)
from app.web.storefront.visitor import create_visitor, ip_key, limit

logger = get_logger(__name__)


router = APIRouter(tags=["storefront-auth"])
BOT_LOGIN_COOKIE = "qb_bot_login"
BOT_LOGIN_TTL_SECONDS = 300
_BOT_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
_BOT_CREDENTIAL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class BotLoginStartIn(BaseModel):
    next: str | None = Field(default=None, max_length=2048)


def _configured_bot_username() -> str | None:
    raw = (settings.telegram_login_bot_username or "").strip().removeprefix("@")
    return raw if _BOT_USERNAME_RE.fullmatch(raw) else None


def _bot_login_credentials(request: Request) -> tuple[str, str] | None:
    value = request.cookies.get(BOT_LOGIN_COOKIE, "")
    token, separator, secret = value.partition(".")
    if (
        not separator
        or len(token) != 32
        or len(secret) != 43
        or not _BOT_CREDENTIAL_RE.fullmatch(token)
        or not _BOT_CREDENTIAL_RE.fullmatch(secret)
    ):
        return None
    return token, secret


async def _require_bot_login_write(request: Request) -> None:
    if request.headers.get("x-bot-login") != "1":
        raise HTTPException(403, "origin_rejected")
    await require_same_origin_write(request)


def _browser_label(user_agent: str) -> str:
    """Reduce UA input to a small, fixed browser/OS label for bot display."""
    agent = user_agent.lower()
    if "edg/" in agent:
        browser = "Edge"
    elif "firefox/" in agent or "fxios/" in agent:
        browser = "Firefox"
    elif "chrome/" in agent or "crios/" in agent:
        browser = "Chrome"
    elif "safari/" in agent:
        browser = "Safari"
    else:
        browser = "Browser"

    if "iphone" in agent or "ipad" in agent or "ipod" in agent:
        platform = "iOS"
    elif "android" in agent:
        platform = "Android"
    elif "windows" in agent:
        platform = "Windows"
    elif "macintosh" in agent or "mac os" in agent:
        platform = "macOS"
    elif "linux" in agent:
        platform = "Linux"
    else:
        platform = "device"
    return f"{browser} on {platform}"


def _no_store(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers={"Cache-Control": "no-store"})


def _bot_login_link(username: str, token: str) -> str:
    return f"https://t.me/{username}?start=login_{quote(token, safe='') }"


def _attach_session(response: Response, request: Request, user: User) -> None:
    assert user.tg_id is not None
    set_session_cookie(
        response,
        request,
        SESSION_COOKIE,
        sign_session(user_id=user.id, tg_id=user.tg_id),
        max_age=settings.web_session_max_age_days * 86400,
    )


async def _claim_browser_cart(
    session: AsyncSession, request: Request, user: User
) -> GuestCartClaim:
    """Use only this request's valid visitor cookie to claim a guest cart."""
    return await claim_guest_cart(session, user, request.cookies.get(GUEST_COOKIE))


def _login_target(target: str, claim: GuestCartClaim) -> str:
    """Route cart collisions through a review step before continuing checkout."""
    return "/basket?msg=web_guest_cart_review" if claim.needs_review else target


def _attach_claimed_session(
    response: Response,
    request: Request,
    user: User,
    claim: GuestCartClaim,
) -> None:
    _attach_session(response, request, user)
    if claim.claimed:
        # Keep the visitor cookie on conflicts and failed claims, so the source
        # cart remains available until the customer resolves it.
        clear_session_cookie(response, request, GUEST_COOKIE)


async def _sign_in(
    session: AsyncSession,
    identity: TelegramIdentity,
    *,
    lang: str,
) -> User | None:
    """Find or create the account behind a proven Telegram identity."""
    repo = UserRepository(session)
    user = await repo.upsert_user(
        tg_id=identity.tg_id,
        username=identity.username,
        full_name=identity.full_name,
        lang=lang,
        referral_source="web",
    )
    if user.is_blocked:
        return None
    await session.flush()
    return user


@router.get("/login")
async def login_page(
    request: Request,
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    target = safe_next(request.query_params.get("next"))
    if user is not None and user.tg_id is not None:
        return RedirectResponse(target, status_code=303)

    return render(
        request,
        "login.html",
        user=None,
        lang=lang,
        next_url=target,
        bot_username=_configured_bot_username(),
        bot_login_enabled=_configured_bot_username() is not None,
        dev_login=settings.web_dev_login_enabled,
    )


@router.post("/auth/bot/start")
async def start_bot_login(
    body: BotLoginStartIn,
    request: Request,
) -> Response:
    await _require_bot_login_write(request)
    username = _configured_bot_username()
    if username is None:
        raise HTTPException(503, "bot_login_unavailable")

    credentials = _bot_login_credentials(request)
    try:
        async with open_bot_login_service() as service:
            if credentials is not None:
                token, secret = credentials
                current = await service.browser_status(token, secret)
                if (
                    current is not None
                    and current.status in {"pending", "claimed", "approved"}
                    and current.expires_in > 0
                ):
                    return _no_store(
                        {
                            "ok": True,
                            "bot_url": _bot_login_link(username, token),
                            "code": current.code,
                            "expires_in": current.expires_in,
                        }
                    )
                await service.cancel(token, secret)

            await limit(
                request,
                f"bot-login-start:{ip_key(request)}",
                10,
                600,
            )
            target = safe_next(body.next, "/account")
            if target in {"/", "/login"}:
                target = "/account"
            challenge = await service.create(
                target,
                _browser_label(request.headers.get("user-agent", "")),
            )
    except BotLoginUnavailable as exc:
        raise HTTPException(503, "bot_login_unavailable") from exc

    response = _no_store(
        {
            "ok": True,
            "bot_url": _bot_login_link(username, challenge.token),
            "code": challenge.code,
            "expires_in": challenge.expires_in,
        }
    )
    max_age = min(BOT_LOGIN_TTL_SECONDS, max(1, int(challenge.expires_in)))
    set_session_cookie(
        response,
        request,
        BOT_LOGIN_COOKIE,
        f"{challenge.token}.{challenge.browser_secret}",
        max_age=max_age,
    )
    return response


@router.get("/auth/bot/status")
async def bot_login_status(request: Request) -> Response:
    credentials = _bot_login_credentials(request)
    if credentials is None:
        return _no_store({"status": "expired", "expires_in": 0})
    token, secret = credentials
    try:
        async with open_bot_login_service() as service:
            state = await service.browser_status(token, secret)
    except BotLoginUnavailable as exc:
        raise HTTPException(503, "bot_login_unavailable") from exc
    if state is None:
        return _no_store({"status": "expired", "expires_in": 0})
    return _no_store(
        {
            "status": state.status,
            "expires_in": max(0, int(state.expires_in)),
        }
    )


@router.post("/auth/bot/complete")
async def complete_bot_login(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _require_bot_login_write(request)
    credentials = _bot_login_credentials(request)
    if credentials is None:
        response = _no_store({"ok": False, "status": "expired"}, status_code=410)
        clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
        return response

    token, secret = credentials
    try:
        async with open_bot_login_service() as service:
            state = await service.browser_status(token, secret)
            if state is None:
                response = _no_store({"ok": False, "status": "expired"}, status_code=410)
                clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
                return response
            if state.status == "denied":
                response = _no_store({"ok": False, "status": "denied"}, status_code=403)
                clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
                return response
            if state.status != "approved" or state.tg_id is None:
                return _no_store({"ok": False, "status": state.status}, status_code=409)

            user = await session.scalar(
                select(User).where(User.tg_id == state.tg_id).with_for_update()
            )
            if user is None:
                await service.cancel(token, secret)
                response = _no_store(
                    {"ok": False, "status": "account_unavailable"}, status_code=403
                )
                clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
                return response
            if user.is_blocked:
                await service.cancel(token, secret)
                response = _no_store(
                    {"ok": False, "status": "blocked", "blocked": True},
                    status_code=403,
                )
                clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
                return response

            consumed_tg_id = await service.consume(token, secret)
            if consumed_tg_id is None or consumed_tg_id != state.tg_id:
                response = _no_store({"ok": False, "status": "expired"}, status_code=410)
                clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
                return response
    except BotLoginUnavailable as exc:
        raise HTTPException(503, "bot_login_unavailable") from exc

    target = safe_next(state.next_path, "/account")
    target_path = urlsplit(target).path.rstrip("/") or "/"
    if target_path in {"/", "/login", "/account"}:
        target = "/manage" if is_admin(user) else "/account"
    claim = await _claim_browser_cart(session, request, user)
    target = _login_target(target, claim)
    response = _no_store({"ok": True, "redirect": target})
    _attach_claimed_session(response, request, user, claim)
    clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
    return response


@router.post("/auth/bot/cancel")
async def cancel_bot_login(request: Request) -> Response:
    await _require_bot_login_write(request)
    credentials = _bot_login_credentials(request)
    if credentials is not None:
        token, secret = credentials
        try:
            async with open_bot_login_service() as service:
                await service.cancel(token, secret)
        except BotLoginUnavailable as exc:
            raise HTTPException(503, "bot_login_unavailable") from exc
    response = _no_store({"ok": True})
    clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
    return response


@router.get("/auth/telegram")
async def telegram_callback() -> Response:
    """Retire the unbound widget callback; use browser-bound bot confirmation."""
    return RedirectResponse("/login?msg=web_login_failed", status_code=303)


@router.post("/auth/webapp")
async def webapp_login(
    body: WebAppLoginIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Response:
    """Sign in silently when the site is opened as a Telegram Mini App."""
    await require_same_origin_write(request)
    identity = verify_webapp_init_data(body.init_data)
    if identity is not None:
        user = await _sign_in(session, identity, lang=lang)
    else:
        return JSONResponse({"ok": False}, status_code=401)
    if user is None:
        return JSONResponse({"ok": False, "blocked": True}, status_code=403)

    claim = await _claim_browser_cart(session, request, user)
    payload: dict[str, Any] = {
        "ok": True,
        "redirect": _login_target(safe_next(body.next), claim),
        "cart_review_required": claim.needs_review,
    }
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store"
    _attach_claimed_session(response, request, user, claim)
    return response


@router.post("/api/session")
async def bootstrap(
    request: Request,
    user: User | None = Depends(current_user),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Response:
    from urllib.parse import urlsplit

    origin = request.headers.get("origin")
    if (
        request.headers.get("sec-fetch-site") == "cross-site"
        or (origin and urlsplit(origin).netloc != request.headers.get("host"))
        or request.headers.get("x-qurbot-bootstrap") != "1"
    ):
        raise HTTPException(403, "origin_rejected")
    if user is not None:
        return JSONResponse({"ok": True, "mode": "guest" if user.tg_id is None else "telegram"})
    if read_session(request.cookies.get(SESSION_COOKIE)) is not None:
        raise HTTPException(403, "account_unavailable")
    return await create_visitor(session, request, lang)


@router.post("/auth/dev")
async def dev_login(
    request: Request,
    tg_id: int = Form(...),
    full_name: str = Form(default="Dev User"),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Response:
    """Local-only sign-in for developing the site without a bot domain.

    Gated on an explicit setting rather than on `app_env`, which defaults to
    "local" -- keying this on the environment name would leave a login bypass
    running in any deployment that forgot to set it.
    """
    if not settings.web_dev_login_enabled:
        return RedirectResponse("/login?msg=web_login_failed", status_code=303)

    identity = TelegramIdentity(tg_id=tg_id, username=None, full_name=full_name, photo_url=None)
    user = await _sign_in(session, identity, lang=lang)
    if user is None:
        return RedirectResponse("/login?msg=web_login_blocked", status_code=303)

    target = safe_next(request.query_params.get("next"))
    claim = await _claim_browser_cart(session, request, user)
    response = RedirectResponse(_login_target(target, claim), status_code=303)
    _attach_claimed_session(response, request, user, claim)
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response, request, SESSION_COOKIE)
    clear_session_cookie(response, request, GUEST_COOKIE)
    clear_session_cookie(response, request, BOT_LOGIN_COOKIE)
    return response
