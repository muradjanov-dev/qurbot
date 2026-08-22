"""Shared plumbing for storefront routes: who is asking, in which language.

Every page needs the same three things -- the signed-in user (or None), the
language to render in, and a template environment that knows both -- so they
are resolved once here rather than in each route.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_catalog_price, format_qty, format_uzs
from app.core.config import settings
from app.core.i18n import t
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db_session
from app.web.storefront.session import LANG_COOKIE, SESSION_COOKIE, normalize_lang, read_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(
    t=t,
    format_uzs=format_uzs,
    format_qty=format_qty,
    format_catalog_price=format_catalog_price,
    settings=settings,
    static_url="/static/store",
)

# Messages a route may hand to the next page through the query string. Kept as
# an allowlist of i18n keys so a redirect can never be used to paint arbitrary
# text -- or someone else's text -- onto our page.
FLASH_KEYS = frozenset(
    {
        "web_saved",
        "web_shop_updated",
        "web_login_failed",
        "web_login_blocked",
        "web_error_generic",
        "web_checkout_login_required",
        "web_shop_import_bad_file",
        "web_shop_import_too_big",
        "web_shop_import_applied",
        "web_added_to_basket",
    }
)


# Strings the browser renders on its own (the basket and quote are drawn
# client-side), shipped with the page so the JS never has to guess a language
# or hold a second copy of the catalogue.
JS_MESSAGE_KEYS: dict[str, str] = {
    "loading": "web_loading",
    "error": "web_error_generic",
    "parseFailed": "web_basket_parse_failed",
    "nothingConfirmed": "web_basket_nothing_confirmed",
    "basketEmpty": "web_basket_empty",
    "basketEmptyHint": "web_basket_empty_hint",
    "basketCount": "web_basket_count",
    "added": "web_added_to_basket",
    "chooseKind": "web_basket_choose_kind",
    "notFound": "web_basket_not_found",
    "remove": "web_delete",
    "quoteEmpty": "web_quote_empty",
    "itemsTotal": "web_quote_items_total",
    "delivery": "web_quote_delivery",
    "grandTotal": "web_quote_grand_total",
    "select": "web_quote_select",
    "pdf": "web_quote_pdf",
    "recalc": "web_quote_recalc",
    "calculate": "web_basket_calculate",
    "loginRequired": "web_checkout_login_required",
    "phoneRequired": "web_checkout_phone_required",
    "addressRequired": "web_checkout_address_required",
    "priceChanged": "web_checkout_price_changed",
    "detecting": "web_checkout_detecting",
    "detectFailed": "web_checkout_detect_failed",
    "detect": "web_checkout_detect",
    "qty": "web_qty",
}


def js_messages(lang: str) -> dict[str, str]:
    """The JS string table for one language.

    Templates keep their placeholders (`{count}`) -- the browser substitutes
    them, so a count can change without a round trip.
    """
    return {name: t(key, lang=lang) for name, key in JS_MESSAGE_KEYS.items()}


def safe_next(raw: str | None, fallback: str = "/") -> str:
    """Only ever redirect back to a path on this site.

    `next` arrives from the query string and is echoed into a Location header,
    so without this the language switcher and the login round trip would both
    be open redirects.
    """
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return fallback
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return fallback
    return raw


async def current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User | None:
    """The signed-in user, or None for a visitor browsing anonymously.

    A blocked account is treated as signed out rather than shown an error: the
    bot already refuses it, and there is nothing useful for them to do here.
    """
    data = read_session(request.cookies.get(SESSION_COOKIE))
    if data is None:
        return None

    user = await UserRepository(session).get_by_tg_id(data.tg_id)
    if user is None or user.is_blocked or user.id != data.user_id:
        return None
    return user


def current_lang(request: Request, user: User | None = Depends(current_user)) -> str:
    """Language for this request: explicit cookie choice first, then account."""
    chosen = normalize_lang(request.cookies.get(LANG_COOKIE))
    if chosen:
        return chosen
    if user is not None:
        return normalize_lang(user.lang) or "uz_latn"
    return "uz_latn"


async def require_api_user(user: User | None = Depends(current_user)) -> User:
    """Guard for JSON endpoints that write on the customer's behalf."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login_required",
        )
    return user


def flash_message(request: Request, lang: str) -> str | None:
    """Translate a `?msg=` flash key, ignoring anything not on the allowlist."""
    key = request.query_params.get("msg")
    if key is None or key not in FLASH_KEYS:
        return None
    count = request.query_params.get("n")
    if count is not None and count.isdigit():
        return t(key, lang=lang, count=int(count))
    return t(key, lang=lang)


def render(
    request: Request,
    template: str,
    *,
    user: User | None,
    lang: str,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    """Render a storefront page with the context every template expects."""
    is_shop_owner = user is not None and user.role in ("shop_owner", "admin")
    is_admin = user is not None and (user.role == "admin" or user.tg_id in settings.admin_tg_ids)
    payload: dict[str, Any] = {
        "user": user,
        "lang": lang,
        "is_shop_owner": is_shop_owner,
        "is_admin": is_admin,
        "flash": flash_message(request, lang),
        "path": request.url.path,
        "js_messages": js_messages(lang),
    }
    payload.update(context)
    return templates.TemplateResponse(request, template, payload, status_code=status_code)
