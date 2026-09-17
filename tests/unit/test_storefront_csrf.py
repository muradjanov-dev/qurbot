import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.web.storefront.security import csrf_token, require_csrf
from app.web.storefront.session import SESSION_COOKIE, sign_session


def request(cookie: str, token: str = "", origin: str | None = None) -> Request:
    headers = [(b"host", b"shop.example"), (b"cookie", f"{SESSION_COOKIE}={cookie}".encode())]
    if token:
        headers.append((b"x-csrf-token", token.encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "headers": headers})


@pytest.mark.asyncio
async def test_csrf_is_bound_to_valid_signed_session() -> None:
    cookie = sign_session(user_id=1, tg_id=10)
    token = csrf_token(request(cookie))
    await require_csrf(request(cookie, token, "https://shop.example"))
    another = sign_session(user_id=2, tg_id=20)
    with pytest.raises(HTTPException) as exc:
        await require_csrf(request(another, token))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("cookie", ["", "tampered", "a.b"])
async def test_invalid_session_cannot_issue_csrf(cookie: str) -> None:
    assert csrf_token(request(cookie)) == ""
    with pytest.raises(HTTPException):
        await require_csrf(request(cookie))


@pytest.mark.asyncio
async def test_cross_origin_and_missing_token_rejected() -> None:
    cookie = sign_session(user_id=1, tg_id=10)
    token = csrf_token(request(cookie))
    for req in (request(cookie), request(cookie, token, "https://attacker.example")):
        with pytest.raises(HTTPException):
            await require_csrf(req)
