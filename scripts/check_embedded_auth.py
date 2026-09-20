"""Real Chrome + actual ASGI/DB auth, isolated from production and Telegram.

Uses a synthetic signed Telegram launch and in-memory SQLite. Every browser
request is intercepted: no real Telegram user, bot token, or model is contacted.
Checks Telegram's cross-site iframe with third-party cookie blocking, as well
as top-level WebViews. Requires Playwright and /usr/bin/google-chrome.
"""

import asyncio
import hmac
import json
import time
from hashlib import sha256
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode, urlsplit

from httpx import ASGITransport, AsyncClient
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.models.user import User
from app.db.session import get_db_session
from app.main import create_app
from app.web.storefront import visitor

ORIGIN = "https://qurbot.test"
PARENT = "https://telegram-frame.test"


def launch_proof() -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 555, "first_name": "Synthetic admin"}),
    }
    key = hmac.new(b"WebAppData", settings.bot_token.encode(), sha256).digest()
    fields["hash"] = hmac.new(
        key, "\n".join(f"{k}={fields[k]}" for k in sorted(fields)).encode(), sha256
    ).hexdigest()
    return urlencode(fields)


async def main() -> None:
    settings.bot_token = "123456:BROWSER_TEST_ONLY"
    settings.web_session_secret = "browser-fixture-key"
    settings.webhook_base_url = ORIGIN
    settings.admin_tg_ids = []
    settings.llm_enabled = settings.agent_enabled = False
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(User(tg_id=555, role="admin", full_name="Synthetic admin"))
        await session.commit()
    lock = asyncio.Lock()

    async def db():
        async with lock, sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db_session] = db
    with patch.object(visitor, "limit", AsyncMock()):
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
            for embedded, guest, legacy in [
                (False, False, False),
                (True, False, True),  # Negative control: reproduces the old 200 -> 401 bug.
                (True, False, False),
                (False, True, False),
                (True, True, False),
            ]:
                context = await browser.new_context(viewport={"width": 390, "height": 760})
                proof = "" if guest else launch_proof()
                entry = "/" if guest else "/login?next=/operator"
                statuses = []
                errors = []

                async def route(r, *, entry=entry, proof=proof, legacy=legacy, statuses=statuses):
                    url = r.request.url
                    if url.startswith(PARENT):
                        return await r.fulfill(
                            content_type="text/html",
                            body=f'<iframe src="{ORIGIN}{entry}"></iframe>',
                        )
                    if url.startswith("https://telegram.org/js/telegram-web-app.js"):
                        return await r.fulfill(
                            content_type="text/javascript",
                            body="window.Telegram={WebApp:{initData:"
                            + json.dumps(proof)
                            + ",ready(){},expand(){}}};",
                        )
                    if not url.startswith(ORIGIN):
                        return await r.abort()
                    # A fresh client MUST NOT retain an httpx cookie jar: only Chrome
                    # decides whether cookies are stored/sent across the frame boundary.
                    async with AsyncClient(transport=ASGITransport(app=app)) as client:
                        response = await client.request(
                            r.request.method,
                            url,
                            headers=await r.request.all_headers(),
                            content=r.request.post_data_buffer,
                        )
                    headers = dict(response.headers)
                    if "set-cookie" in headers:
                        cookies = response.headers.get_list("set-cookie")
                        if legacy:
                            cookies = [
                                c.replace("SameSite=none", "SameSite=lax").replace(
                                    "; Partitioned", ""
                                )
                                for c in cookies
                            ]
                        headers["set-cookie"] = "\n".join(cookies)
                    statuses.append((urlsplit(url).path, response.status_code))
                    await r.fulfill(
                        status=response.status_code, headers=headers, body=response.content
                    )

                await context.route("**/*", route)
                page = await context.new_page()
                page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                cdp = await context.new_cdp_session(page)
                await cdp.send("Network.enable")
                await cdp.send(
                    "Network.setCookieControls",
                    {
                        "enableThirdPartyCookieRestriction": True,
                        "disableThirdPartyCookieMetadata": True,
                        "disableThirdPartyCookieHeuristics": True,
                    },
                )
                await page.goto(PARENT if embedded else ORIGIN + entry)
                frame = page.frames[1] if embedded else page.main_frame
                if legacy:
                    await frame.locator("[data-telegram-auth]:not([hidden])").wait_for()
                    assert ("/auth/webapp", 200) in statuses
                    assert ("/api/cart", 401) in statuses
                else:
                    await frame.locator('body[data-authed="1"]').wait_for()
                    expected = 403 if guest else 200
                    assert (
                        await frame.evaluate(
                            "async () => (await fetch('/api/chat/operator')).status"
                        )
                        == expected
                    )
                    await frame.goto(frame.url)
                    await frame.locator('body[data-authed="1"]').wait_for()
                    assert (
                        await frame.evaluate("async () => (await fetch('/api/cart')).status") == 200
                    )
                    assert "qb_session" not in await frame.evaluate("document.cookie")
                    assert "qb_visitor" not in await frame.evaluate("document.cookie")
                    await frame.evaluate(
                        "async () => await fetch('/logout',{method:'POST',redirect:'manual'})"
                    )
                    assert (
                        await frame.evaluate("async () => (await fetch('/api/cart')).status") == 401
                    )
                    assert not errors, errors
                print(
                    json.dumps({"embedded": embedded, "guest": guest, "legacy": legacy, "ok": True})
                )
                await context.close()
            await browser.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
