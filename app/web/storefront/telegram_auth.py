"""Verifying that a visitor really is the Telegram account they claim.

Two doorways, one proof. The Login Widget (a browser tab) and a Mini App
(the site opened inside Telegram) both hand over a payload signed with a key
derived from the bot token, so both can be checked offline -- no call back to
Telegram, no shared secret beyond the token the deployment already holds.

The two use *different* derivations, and that difference is the whole security
boundary: a widget payload cannot be replayed as Mini App init data or the
other way round.
"""

from __future__ import annotations

import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import parse_qsl

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    """A Telegram account whose ownership has been proven to us."""

    tg_id: int
    username: str | None
    full_name: str | None
    photo_url: str | None


def _data_check_string(fields: Mapping[str, str]) -> str:
    return "\n".join(f"{key}={fields[key]}" for key in sorted(fields) if key != "hash")


def _is_fresh(auth_date: str | None, *, now: int | None) -> bool:
    """Whether the payload was signed recently enough to still be trusted."""
    if auth_date is None:
        return False
    try:
        signed_at = int(auth_date)
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if signed_at > current + 60:
        return False
    return current - signed_at <= settings.web_login_max_age_seconds


def _full_name(first: str | None, last: str | None) -> str | None:
    parts = [part for part in (first, last) if part]
    return " ".join(parts) if parts else None


def verify_login_widget(
    params: Mapping[str, str],
    *,
    bot_token: str | None = None,
    now: int | None = None,
) -> TelegramIdentity | None:
    """Check a Telegram Login Widget callback (`?id=&hash=&auth_date=…`).

    Per Telegram's login documentation the key is `sha256(bot_token)` and the
    signed material is every field except `hash`, sorted by name.
    """
    provided = params.get("hash")
    if not provided:
        return None
    if not _is_fresh(params.get("auth_date"), now=now):
        return None

    token = bot_token if bot_token is not None else settings.bot_token
    secret_key = sha256(token.encode()).digest()
    expected = hmac.new(secret_key, _data_check_string(params).encode(), sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        return None

    raw_id = params.get("id")
    if raw_id is None or not raw_id.lstrip("-").isdigit():
        return None

    return TelegramIdentity(
        tg_id=int(raw_id),
        username=params.get("username") or None,
        full_name=_full_name(params.get("first_name"), params.get("last_name")),
        photo_url=params.get("photo_url") or None,
    )


def verify_webapp_init_data(
    init_data: str,
    *,
    bot_token: str | None = None,
    now: int | None = None,
) -> TelegramIdentity | None:
    """Check `Telegram.WebApp.initData` from the site running inside Telegram.

    Per Telegram's Mini Apps documentation the key here is
    `HMAC_SHA256("WebAppData", bot_token)` -- keyed the other way round from the
    Login Widget, which is what keeps one payload from being replayed as the
    other.
    """
    if not init_data:
        return None

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    provided = fields.get("hash")
    if not provided:
        return None
    if not _is_fresh(fields.get("auth_date"), now=now):
        return None

    token = bot_token if bot_token is not None else settings.bot_token
    secret_key = hmac.new(b"WebAppData", token.encode(), sha256).digest()
    expected = hmac.new(secret_key, _data_check_string(fields).encode(), sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        return None

    try:
        user = json.loads(fields.get("user", "null"))
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict):
        return None

    tg_id = user.get("id")
    if not isinstance(tg_id, int):
        return None

    return TelegramIdentity(
        tg_id=tg_id,
        username=user.get("username") or None,
        full_name=_full_name(user.get("first_name"), user.get("last_name")),
        photo_url=user.get("photo_url") or None,
    )
