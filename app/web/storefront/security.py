"""Session-bound CSRF protection for authenticated storefront mutations."""

import hmac
from hashlib import sha256
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.core.config import settings
from app.web.storefront.session import GUEST_COOKIE, SESSION_COOKIE, read_session


async def require_same_origin_write(request: Request) -> None:
    """Do not rely on SameSite cookies to protect legacy HTML form mutations."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "origin_rejected")
    if origin:
        parsed = urlsplit(origin)
        if parsed.netloc != request.headers.get("host") or parsed.scheme not in {"http", "https"}:
            raise HTTPException(403, "origin_rejected")


def csrf_token(request: Request) -> str:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if read_session(cookie) is None:
        cookie = request.cookies.get(GUEST_COOKIE, "")
        if len(cookie) != 43:
            return ""
    return hmac.new(settings.web_session_key, f"csrf:{cookie}".encode(), sha256).hexdigest()


async def require_csrf(request: Request) -> None:
    expected = csrf_token(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="csrf_rejected")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        # Compare authorities, including port. The reverse proxy retains Host.
        if parsed.netloc != request.headers.get("host") or parsed.scheme not in {"http", "https"}:
            raise HTTPException(status_code=403, detail="csrf_rejected")
