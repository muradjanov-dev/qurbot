"""Session cookies and Telegram login proofs.

These are the storefront's only authentication, so the tests are written from
the attacker's side: what happens to a payload that was edited, replayed late,
or signed with the wrong key.
"""

from __future__ import annotations

import hmac
import json
import time
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode

from app.core.config import settings
from app.web.storefront.session import read_session, sign_session
from app.web.storefront.telegram_auth import verify_login_widget, verify_webapp_init_data

BOT_TOKEN = "123456:TEST-TOKEN"


def _widget_params(**overrides: str) -> dict[str, str]:
    params: dict[str, str] = {
        "id": "917456291",
        "first_name": "Ali",
        "username": "ali",
        "auth_date": str(int(time.time())),
    }
    params.update(overrides)
    check = "\n".join(f"{key}={params[key]}" for key in sorted(params))
    secret = sha256(BOT_TOKEN.encode()).digest()
    params["hash"] = hmac.new(secret, check.encode(), sha256).hexdigest()
    return params


def _init_data(**overrides: str) -> str:
    fields: dict[str, str] = {
        "auth_date": str(int(time.time())),
        "query_id": "AAF",
        "user": json.dumps({"id": 555, "first_name": "Bek", "username": "bek"}),
    }
    fields.update(overrides)
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), sha256).hexdigest()
    return urlencode(fields)


# ── session cookie ──────────────────────────────────────────────────────


def test_session_round_trip() -> None:
    token = sign_session(user_id=7, tg_id=917456291)
    data = read_session(token)
    assert data is not None
    assert (data.user_id, data.tg_id) == (7, 917456291)


def test_session_rejects_tampered_payload() -> None:
    token = sign_session(user_id=7, tg_id=1)
    payload, signature = token.split(".", 1)
    forged = sign_session(user_id=99, tg_id=2).split(".", 1)[0]
    assert read_session(f"{forged}.{signature}") is None
    assert read_session(f"{payload}.{'a' * len(signature)}") is None


def test_session_rejects_garbage() -> None:
    for value in (None, "", "nodot", "a.b.c", "!!!.???"):
        assert read_session(value) is None


def test_session_expires() -> None:
    issued = int(time.time()) - settings.web_session_max_age_days * 86400 - 10
    token = sign_session(user_id=7, tg_id=1, now=issued)
    assert read_session(token) is None
    # ...and is still valid a moment before that.
    fresh = sign_session(user_id=7, tg_id=1, now=issued + 60)
    assert read_session(fresh) is not None


def test_session_rejects_future_issue_date() -> None:
    token = sign_session(user_id=7, tg_id=1, now=int(time.time()) + 3600)
    assert read_session(token) is None


# ── Telegram login widget ───────────────────────────────────────────────


def test_login_widget_accepts_valid_signature() -> None:
    identity = verify_login_widget(_widget_params(), bot_token=BOT_TOKEN)
    assert identity is not None
    assert identity.tg_id == 917456291
    assert identity.full_name == "Ali"


def test_login_widget_rejects_edited_field() -> None:
    params = _widget_params()
    params["id"] = "999"
    assert verify_login_widget(params, bot_token=BOT_TOKEN) is None


def test_login_widget_rejects_stale_payload() -> None:
    stale = str(int(time.time()) - settings.web_login_max_age_seconds - 60)
    assert verify_login_widget(_widget_params(auth_date=stale), bot_token=BOT_TOKEN) is None


def test_login_widget_rejects_other_bot_token() -> None:
    assert verify_login_widget(_widget_params(), bot_token="999:OTHER") is None


def test_login_widget_rejects_missing_hash() -> None:
    params = _widget_params()
    del params["hash"]
    assert verify_login_widget(params, bot_token=BOT_TOKEN) is None


# ── Mini App init data ──────────────────────────────────────────────────


def test_webapp_init_data_accepts_valid_signature() -> None:
    identity = verify_webapp_init_data(_init_data(), bot_token=BOT_TOKEN)
    assert identity is not None
    assert identity.tg_id == 555
    assert identity.username == "bek"


def test_webapp_init_data_rejects_edited_user() -> None:
    fields = dict(parse_qsl(_init_data()))
    fields["user"] = json.dumps({"id": 1})
    assert verify_webapp_init_data(urlencode(fields), bot_token=BOT_TOKEN) is None


def test_webapp_and_widget_keys_are_not_interchangeable() -> None:
    """A widget payload must not pass as init data, nor the other way round.

    The two derive their key from the bot token differently; if either check
    accepted the other's signature, one stolen payload would open both doors.
    """
    widget = _widget_params()
    assert verify_webapp_init_data(urlencode(widget), bot_token=BOT_TOKEN) is None

    assert verify_login_widget(dict(parse_qsl(_init_data())), bot_token=BOT_TOKEN) is None
