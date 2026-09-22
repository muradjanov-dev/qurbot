"""Offline browser regression for the chat viewport; see docs/CHAT_LAYOUT.md.

Uses the real templates/CSS/JavaScript and mocked HTTP, never production data.
Playwright is an optional local verification tool, not a runtime dependency.
"""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import Browser, Route, sync_playwright

from app.core.config import settings
from app.core.i18n import t

ROOT = Path(__file__).resolve().parents[1]
(ROOT / ".artifacts").mkdir(exist_ok=True)
env = Environment(loader=FileSystemLoader(ROOT / "app/web/storefront/templates"), autoescape=True)
env.globals.update(
    t=t, csrf_token=lambda request: "test-csrf", asset_version="browser-check", settings=settings
)


def check_case(browser: Browser, width: int, height: int, lang: str) -> None:
    page = browser.new_page(viewport={"width": width, "height": height}, color_scheme="dark")
    page.add_init_script("""window.Telegram = {WebApp: {
        get viewportHeight() { return this.testHeight || innerHeight; },
        ready() {}, expand() {},
        onEvent(name, callback) { this[name] = callback; }
    }};""")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    messages = [
        {
            "id": i,
            "sequence": i,
            "role": "user" if i % 2 else "assistant",
            "text": f"{i}. Test message\nSecond line",
            "cards": [],
        }
        for i in range(1, 41)
    ]
    html = env.get_template("chat.html").render(
        lang=lang,
        user=object(),
        path="/chat",
        static_url="/static/store",
        js_messages={},
        request=None,
    )

    def route(request: Route) -> None:
        path = urlsplit(request.request.url).path
        if path.startswith("/static/store/"):
            file = ROOT / "app/web/storefront/static" / path.split("/")[-1]
            request.fulfill(path=str(file))
        elif path.startswith("/api/chat"):
            if request.request.method == "POST":
                payload = request.request.post_data_json
                if "text" in payload:
                    messages.append(
                        {
                            "id": len(messages) + 1,
                            "sequence": len(messages) + 1,
                            "role": "user",
                            "text": payload["text"],
                        }
                    )
                    request.fulfill(
                        json={
                            "status": "human",
                            "request_id": payload["request_id"],
                            "messages": messages,
                        }
                    )
                    return
            request.fulfill(
                json={
                    "conversation_id": "test",
                    "status": "ai",
                    "messages": messages,
                    "requests": [],
                }
            )
        elif path.startswith("/api/cart"):
            request.fulfill(json={"revision": 1, "lines": []})
        elif path == "/chat":
            request.fulfill(body=html, content_type="text/html")
        else:
            request.fulfill(body="", content_type="application/javascript")

    page.route("**/*", route)
    page.goto("https://chat.test/chat")
    page.wait_for_function("!document.querySelector('#chat-message').disabled")

    def check_layout() -> None:
        metrics = page.evaluate("""() => {
            const box = s => document.querySelector(s).getBoundingClientRect();
            const composer = box('[data-chat-form]'), log = box('[data-chat-log]');
            const input = box('#chat-message'), send = box('[data-chat-send]');
            return {composerBottom: composer.bottom, composerTop: composer.top,
                logBottom: log.bottom,
                inputRight: input.right, inputBottom: input.bottom,
                sendLeft: send.left, sendBottom: send.bottom,
                tabTop: innerHeight, height: innerHeight,
                pageHeight: document.documentElement.scrollHeight,
                pageWidth: document.documentElement.scrollWidth,
                width: innerWidth,
                visibleHeight: Math.min(innerHeight, Telegram.WebApp.viewportHeight)};
        }""")
        print(json.dumps({"size": [width, height], "lang": lang, **metrics}))
        assert (
            metrics["composerBottom"] <= metrics["tabTop"] + 1
        ), "Composer is below the visible chat / behind navigation"
        assert (
            metrics["composerBottom"] <= metrics["visibleHeight"] + 1
        ), "Composer is behind the keyboard"
        assert metrics["pageHeight"] <= metrics["height"] + 1, "Chat causes outer page scrolling"
        assert metrics["pageWidth"] <= metrics["width"], "Horizontal overflow"
        assert metrics["logBottom"] <= metrics["composerTop"] + 1, "Composer overlaps history"
        assert (
            abs(metrics["composerBottom"] - metrics["visibleHeight"]) <= 1
        ), "Composer must sit at the bottom of the window, without site navigation"
        assert page.locator(".topbar").count() == 0, "Chat must have only its own header"
        assert page.locator(".footer, .tabbar").count() == 0, "Site chrome must not enter chat"
        assert metrics["sendLeft"] >= metrics["inputRight"], "Send must be beside the input"
        assert abs(metrics["sendBottom"] - metrics["inputBottom"]) <= 1

    page.screenshot(path=str(ROOT / f".artifacts/chat-{width}-{height}.png"))
    check_layout()
    page.locator("#chat-message").fill("Test input\n" * 12)
    check_layout()
    page.locator("[data-chat-send]").click()
    page.wait_for_function("document.querySelector('#chat-message').value === ''")
    check_layout()
    # Telegram's viewport can shrink without changing window.innerHeight.
    page.evaluate("Telegram.WebApp.testHeight = 320; Telegram.WebApp.viewportChanged()")
    page.wait_for_function("document.body.getBoundingClientRect().height === 320")
    check_layout()
    page.evaluate("Telegram.WebApp.testHeight = 0; Telegram.WebApp.viewportChanged()")
    page.set_viewport_size({"width": width, "height": 380})
    page.wait_for_function("document.body.getBoundingClientRect().height === 380")
    check_layout()
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_function(f"document.body.getBoundingClientRect().height === {height}")
    if width == 390 and height == 700:
        page.locator(".chat-menu summary").click()
        assert page.locator("[data-chat-operator]").is_visible()
        assert page.locator("[data-open-cart]").is_visible()
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("[data-chat-operator]").click()
        assert not page.locator(".chat-menu").evaluate("menu => menu.open")
        # New messages must not pull someone away from older history.
        page.locator("[data-chat-log]").evaluate("(log) => { log.scrollTop = 0; }")
        page.wait_for_timeout(100)
        messages.append({"id": 99, "sequence": 99, "role": "assistant", "text": "New reply"})
        page.wait_for_function(
            "document.querySelector('[data-chat-log]').textContent.includes('New reply')"
        )
        assert page.locator("[data-chat-log]").evaluate("(log) => log.scrollTop") == 0
    assert not errors, errors
    page.close()


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        for width, height, lang in [
            (390, 700, "uz_latn"),
            (320, 568, "ru"),
            (500, 790, "uz_cyrl"),
            (1280, 800, "uz_latn"),
            (390, 380, "uz_latn"),
        ]:
            check_case(browser, width, height, lang)
        browser.close()


if __name__ == "__main__":
    main()
