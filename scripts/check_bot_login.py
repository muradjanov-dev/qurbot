"""Browser acceptance for bot-confirmed sign-in on isolated Docker staging.

Telegram transport is covered by handler tests. This script approves only its
own synthetic challenges inside the staging container; it never contacts Telegram.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

SIMULATE = """
import asyncio, json, sys
from app.services.bot_login import open_bot_login_service
from app.core.config import settings
assert settings.app_env in {"local", "staging", "test"}, "refuse production"
assert not settings.register_webhook and not settings.telegram_notifications_enabled
assert settings.bot_token == "123456:STAGING_NO_REAL_TELEGRAM_TOKEN"
async def run():
    token, tg, action = sys.argv[1:]
    async with open_bot_login_service() as service:
        if action == 'expire':
            await service._redis.pexpire(service._key(token), 1)
            print(json.dumps({'ok': True}))
            return
        state = await service.claim(token, int(tg))
        assert state is not None
        success = await service.decide(token, int(tg), approve=(action == 'approve'))
        print(json.dumps({'ok': success, 'code': state.code}))
asyncio.run(run())
"""


def check(base_url: str, container: str) -> None:
    if urlsplit(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Only isolated loopback staging is allowed")
    if not any(label in container for label in ("staging", "admin-review")):
        raise ValueError("Refuse non-staging container")
    output = Path(".artifacts/bot-login")
    output.mkdir(parents=True, exist_ok=True)
    headers = {"X-Bot-Login": "1"}
    errors = []

    def decide(token, tg, action):
        result = subprocess.run(
            ["docker", "exec", container, "python", "-c", SIMULATE, token, tg, action],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)

        def context(width=390, blocked_popup=False):
            ctx = browser.new_context(base_url=base_url, viewport={"width": width, "height": 844})
            ctx.route("https://telegram.org/**", lambda route: route.abort())
            ctx.route(
                "https://t.me/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<p>Isolated Telegram test transport</p>",
                ),
            )
            if blocked_popup:
                ctx.add_init_script("window.open = () => null")
            ctx.request.get("/lang/uz_latn?next=/login")
            page = ctx.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("/login?next=/account")
            assert page.locator('[data-bot-login-enabled="1"]').count() == 1
            return ctx, page

        def start(page):
            page.locator("[data-bot-start]").click()
            page.wait_for_function(
                "/^[0-9]{6}$/.test(document.querySelector('[data-bot-code]').textContent)"
            )
            code = page.locator("[data-bot-code]").inner_text()
            link = page.locator("[data-bot-open]").get_attribute("href")
            token = parse_qs(urlsplit(link).query)["start"][0].removeprefix("login_")
            assert re.fullmatch(r"[A-Za-z0-9_-]{32}", token)
            page.bring_to_front()
            return token, code

        for tg, destination in (("499990001", "/manage"), ("499990002", "/account")):
            ctx, page = context()
            token, code = start(page)
            challenge_cookie = next(c for c in ctx.cookies() if c["name"] == "qb_bot_login")
            assert challenge_cookie["httpOnly"]
            page.screenshot(path=str(output / f"pending-{tg[-1]}.png"))
            other = browser.new_context(base_url=base_url)
            denied = other.request.post(
                "/auth/bot/complete", headers=headers, data={"token": token}
            )
            assert denied.status == 410
            assert not any(c["name"] == "qb_session" for c in other.cookies())
            other.close()
            result = decide(token, tg, "approve")
            assert result["ok"] and result["code"] == code
            page.bring_to_front()
            page.wait_for_url(
                lambda url, target=destination: urlsplit(url).path == target, timeout=12000
            )
            assert any(c["name"] == "qb_session" and c["httpOnly"] for c in ctx.cookies())
            replay = ctx.request.post("/auth/bot/complete", headers=headers, data={})
            assert replay.status == 410
            assert ctx.request.get(destination).ok
            page.screenshot(path=str(output / f"signed-in-{tg[-1]}.png"))
            ctx.close()

        ctx, page = context(blocked_popup=True)
        token, _ = start(page)
        assert page.locator("[data-bot-open]").is_visible()
        assert decide(token, "499990002", "deny")["ok"]
        page.wait_for_function(
            "document.querySelector('[data-bot-status]').dataset.state==='denied'"
        )
        assert not any(c["name"] == "qb_session" for c in ctx.cookies())
        page.locator("[data-bot-retry]").click()
        page.wait_for_function("document.querySelector('[data-bot-session]').hidden===false")
        page.locator("[data-bot-cancel]").click()
        page.wait_for_function(
            "document.querySelector('[data-bot-status]').dataset.state==='cancelled'"
        )
        ctx.close()

        ctx, page = context(320, blocked_popup=True)
        token, _ = start(page)
        decide(token, "499990002", "expire")
        page.wait_for_function(
            "document.querySelector('[data-bot-status]').dataset.state==='expired'"
        )
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
        page.screenshot(path=str(output / "expired-mobile.png"))
        ctx.close()

        ctx, page = context(blocked_popup=True)
        ctx.route(
            "**/auth/bot/start",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body='{"detail":"bot_login_unavailable"}',
            ),
        )
        page.locator("[data-bot-start]").click()
        page.wait_for_function(
            "document.querySelector('[data-bot-status]').dataset.state==='error'"
        )
        assert page.locator("[data-bot-session]").is_hidden()
        assert page.locator("[data-bot-retry]").is_visible()
        ctx.close()
        browser.close()
    assert not errors, errors
    print(
        "PASS: original-browser admin/customer sign-in, cross-browser rejection, replay, "
        "denial, cancel, expiry, popup fallback and server failure"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081")
    parser.add_argument("--container", default="qurbot-admin-review-web-1")
    args = parser.parse_args()
    check(args.base_url, args.container)
