"""Signed session cookies for the storefront.

A session is a signed statement of "this browser is Telegram user N", nothing
more: no server-side store, so it survives a restart and a second web replica
without Redis being in the path. The signature is what makes it safe -- the
payload is readable by the client but cannot be edited, and it carries an
issue time so a stolen cookie expires on its own.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.core.config import settings

SESSION_COOKIE = "qb_session"
LANG_COOKIE = "qb_lang"

SUPPORTED_LANGS = ("uz_latn", "uz_cyrl", "ru")


@dataclass(frozen=True, slots=True)
class SessionData:
    """What a valid session cookie asserts."""

    user_id: int
    tg_id: int
    issued_at: int


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _signature(payload: str) -> str:
    digest = hmac.new(settings.web_session_key, payload.encode(), sha256).digest()
    return _b64encode(digest)


def sign_session(*, user_id: int, tg_id: int, now: int | None = None) -> str:
    """Build the cookie value for a signed-in user."""
    issued_at = int(now if now is not None else time.time())
    body: dict[str, Any] = {"uid": user_id, "tg": tg_id, "iat": issued_at}
    payload = _b64encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    return f"{payload}.{_signature(payload)}"


def read_session(token: str | None, *, now: int | None = None) -> SessionData | None:
    """Validate a cookie value, returning None for anything untrustworthy.

    Every failure mode -- tampered payload, wrong signature, expired, garbage --
    collapses to None on purpose: the caller's only sensible response to any of
    them is to treat the visitor as signed out.
    """
    if not token or token.count(".") != 1:
        return None

    payload, provided = token.split(".", 1)
    if not hmac.compare_digest(_signature(payload), provided):
        return None

    try:
        body = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None

    user_id = body.get("uid")
    tg_id = body.get("tg")
    issued_at = body.get("iat")
    if not isinstance(user_id, int) or not isinstance(tg_id, int):
        return None
    if not isinstance(issued_at, int):
        return None

    current = int(now if now is not None else time.time())
    max_age = settings.web_session_max_age_days * 86400
    if issued_at > current + 60 or current - issued_at > max_age:
        # A future-dated cookie is as suspicious as an expired one; the 60s of
        # slack is for clock skew between replicas, not for tolerating forgery.
        return None

    return SessionData(user_id=user_id, tg_id=tg_id, issued_at=issued_at)


def normalize_lang(value: str | None) -> str | None:
    """Accept only the three languages the catalogues actually carry."""
    if value in SUPPORTED_LANGS:
        return value
    return None
