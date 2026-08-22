"""Signing in with Telegram, and signing out.

Two doorways into the same account: the Login Widget for a browser tab, and
Mini App init data for the site opened inside Telegram. Both prove ownership of
a Telegram id offline (see `telegram_auth`), and both end at the same place --
a signed cookie naming the `users` row the bot already knows.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db_session
from app.web.storefront.deps import current_lang, current_user, render, safe_next
from app.web.storefront.schemas import WebAppLoginIn
from app.web.storefront.session import SESSION_COOKIE, sign_session
from app.web.storefront.telegram_auth import (
    TelegramIdentity,
    verify_login_widget,
    verify_webapp_init_data,
)

logger = get_logger(__name__)

router = APIRouter(tags=["storefront-auth"])


def _cookie_is_secure(request: Request) -> bool:
    """Whether to mark the session cookie Secure.

    Behind Railway's proxy the app often sees plain http even though the
    browser is on https, so the configured public URL gets a say too.
    """
    return request.url.scheme == "https" or settings.webhook_base_url.startswith("https://")


def _attach_session(response: Response, request: Request, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user_id=user.id, tg_id=user.tg_id),
        max_age=settings.web_session_max_age_days * 86400,
        httponly=True,
        secure=_cookie_is_secure(request),
        samesite="lax",
    )


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
    if user is not None:
        return RedirectResponse(target, status_code=303)

    return render(
        request,
        "login.html",
        user=None,
        lang=lang,
        next_url=target,
        bot_username=settings.telegram_login_bot_username,
        dev_login=settings.web_dev_login_enabled,
    )


@router.get("/auth/telegram")
async def telegram_callback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Response:
    """Where the Telegram Login Widget sends the browser back to."""
    params = dict(request.query_params)
    target = safe_next(params.pop("next", None))

    identity = verify_login_widget(params)
    if identity is None:
        logger.warning("web_login_rejected", reason="bad_signature")
        return RedirectResponse("/login?msg=web_login_failed", status_code=303)

    user = await _sign_in(session, identity, lang=lang)
    if user is None:
        return RedirectResponse("/login?msg=web_login_blocked", status_code=303)

    response = RedirectResponse(target, status_code=303)
    _attach_session(response, request, user)
    return response


@router.post("/auth/webapp")
async def webapp_login(
    body: WebAppLoginIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Response:
    """Sign in silently when the site is opened as a Telegram Mini App."""
    identity = verify_webapp_init_data(body.init_data)
    if identity is None:
        return JSONResponse({"ok": False}, status_code=401)

    user = await _sign_in(session, identity, lang=lang)
    if user is None:
        return JSONResponse({"ok": False, "blocked": True}, status_code=403)

    payload: dict[str, Any] = {"ok": True, "redirect": safe_next(body.next)}
    response = JSONResponse(payload)
    _attach_session(response, request, user)
    return response


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

    response = RedirectResponse(safe_next(request.query_params.get("next")), status_code=303)
    _attach_session(response, request, user)
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
