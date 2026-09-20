"""HttpOnly sessions usable both directly and inside Telegram's cross-site frame."""

from fastapi import Request, Response

from app.core.config import settings


def cookie_is_secure(request: Request) -> bool:
    return request.url.scheme == "https" or settings.webhook_base_url.startswith("https://")


def set_session_cookie(
    response: Response, request: Request, name: str, value: str, *, max_age: int
) -> None:
    secure = cookie_is_secure(request)
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
    )
    if secure:
        # Python 3.12's SimpleCookie / Starlette cannot serialize partitioned=True.
        # Append to ONLY the cookie just emitted; never replace other Set-Cookie fields.
        key, header = response.raw_headers[-1]
        assert key == b"set-cookie"
        response.raw_headers[-1] = (key, header + b"; Partitioned")


def clear_session_cookie(response: Response, request: Request, name: str) -> None:
    # Clear both the pre-fix unpartitioned cookie and the current partition.
    response.delete_cookie(name, secure=cookie_is_secure(request), httponly=True)
    set_session_cookie(response, request, name, "", max_age=0)
