import pytest
from fastapi import Request, Response

from app.core.config import settings
from app.web.storefront.cookies import clear_session_cookie, set_session_cookie


@pytest.mark.parametrize(
    "scheme,public_url,secure",
    [("https", "", True), ("http", "https://shop.example", True), ("http", "", False)],
)
def test_session_cookie_policy(monkeypatch, scheme, public_url, secure):
    monkeypatch.setattr(settings, "webhook_base_url", public_url)
    request = Request(
        {"type": "http", "scheme": scheme, "path": "/", "headers": [(b"host", b"shop.test")]}
    )
    response = Response()
    response.set_cookie("unrelated", "preserved")
    set_session_cookie(response, request, "qb_session", "signed", max_age=60)
    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 2 and "Partitioned" not in headers[0]
    assert "HttpOnly" in headers[1] and "Path=/" in headers[1]
    assert ("SameSite=none" in headers[1]) is secure
    assert ("Partitioned" in headers[1]) is secure
    assert ("Secure" in headers[1]) is secure
    if not secure:
        assert "SameSite=lax" in headers[1]
    clear_session_cookie(response, request, "qb_session")
    deleted = response.headers.getlist("set-cookie")[-2:]
    assert all("Max-Age=0" in value for value in deleted)
    assert "Partitioned" not in deleted[0]
    assert ("Partitioned" in deleted[1]) is secure
