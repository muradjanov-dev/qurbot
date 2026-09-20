"""Offline browser regression: long operator threads/inbox must scroll independently.

Real templates/CSS/JS, synthetic HTTP only. Requires optional Playwright and Chrome.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from app.core.i18n import t

ROOT = Path(__file__).resolve().parents[1]


def check(browser, width, height, lang):
    page = browser.new_page(viewport={"width": width, "height": height}, color_scheme="dark")
    page.add_init_script("""window.Telegram = {WebApp: {
        get viewportHeight() { return this.testHeight || innerHeight; },
        onEvent(name, callback) { this[name] = callback; }, ready() {}, expand() {}
    }};""")
    env = Environment(
        loader=FileSystemLoader(ROOT / "app/web/storefront/templates"), autoescape=True
    )
    env.globals.update(t=t, csrf_token=lambda request: "fixture", asset_version="scroll-test")
    html = env.get_template("operator.html").render(
        user=SimpleNamespace(id=1, tg_id=1),
        lang=lang,
        path="/operator",
        static_url="/static/store",
        js_messages={},
        request=None,
    )
    messages = [
        {
            "id": i,
            "sequence": i,
            "role": "user" if i % 2 else "assistant",
            "text": f"{i}. Fanera 1.525x1.525\n15 mm — 20 dona\n3 mm — 10 dona",
        }
        for i in range(1, 61)
    ]
    rows = [
        {
            "id": i,
            "user_id": i,
            "name": f"Test customer {i}",
            "status": "human",
            "mine": False,
            "preview": "Fanera kerak",
            "unread": 1,
            "updated_at": "2026-09-21T10:00:00Z",
        }
        for i in range(1, 41)
    ]
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def route(r):
        url = urlsplit(r.request.url)
        if url.path.startswith("/static/store/"):
            r.fulfill(path=str(ROOT / "app/web/storefront/static" / url.path.split("/")[-1]))
        elif url.path == "/operator":
            r.fulfill(body=html, content_type="text/html")
        elif url.path == "/api/chat/operator":
            r.fulfill(json={"conversations": rows, "next_cursor": None})
        elif url.path == "/api/chat/operator/1":
            after = int(parse_qs(url.query).get("after", [0])[0])
            r.fulfill(
                json={
                    "status": "human",
                    "operator_id": 2,
                    "messages": [m for m in messages if m["sequence"] > after],
                }
            )
        elif url.path.endswith("/read"):
            r.fulfill(json={"ok": True})
        elif url.path == "/api/cart":
            r.fulfill(json={"ok": True, "revision": 0, "lines": []})
        else:
            r.fulfill(body="", content_type="application/javascript")

    page.route("**/*", route)
    page.goto("https://operator.test/operator?conversation=1")
    page.wait_for_function("document.querySelectorAll('.chat-message').length === 60")
    log = page.locator("[data-thread-log]")

    def layout():
        metrics = page.evaluate("""() => {
            const log = document.querySelector('[data-thread-log]');
            const form = document.querySelector('[data-operator-form]').getBoundingClientRect();
            return {height: Math.min(innerHeight, Telegram.WebApp.viewportHeight),
                composerBottom: form.bottom, logBottom: log.getBoundingClientRect().bottom,
                composerTop: form.top, logHeight: log.clientHeight, contentHeight: log.scrollHeight,
                pageHeight: document.documentElement.scrollHeight, windowHeight: innerHeight};
        }""")
        print(json.dumps({"viewport": [width, height], **metrics}))
        assert (
            0 < metrics["logHeight"] < metrics["contentHeight"]
        ), "History has no scrollable viewport"
        assert metrics["composerBottom"] <= metrics["height"] + 1, "Composer clipped below WebApp"
        assert metrics["logBottom"] <= metrics["composerTop"] + 1
        assert metrics["pageHeight"] <= metrics["windowHeight"] + 1, "Outer page overflow"

    layout()
    log.evaluate("node => { node.scrollTop = 0; }")
    log.hover()
    page.mouse.wheel(0, 500)
    page.wait_for_function("document.querySelector('[data-thread-log]').scrollTop > 100")
    if width <= 760:
        log.evaluate("node => { node.scrollTop = 0; }")
        touch = page.context.new_cdp_session(page)
        touch.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        box = log.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] - 40
        for kind, delta in [
            ("touchStart", 0),
            ("touchMove", 60),
            ("touchMove", 120),
            ("touchMove", 180),
            ("touchEnd", 180),
        ]:
            # Hold before lifting to test a drag, not a high-velocity fling.
            page.wait_for_timeout(250 if kind == "touchEnd" else 60)
            touch.send(
                "Input.dispatchTouchEvent",
                {
                    "type": kind,
                    "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y - delta}],
                },
            )
        page.wait_for_function("document.querySelector('[data-thread-log]').scrollTop > 50")
        touch.send("Emulation.setTouchEmulationEnabled", {"enabled": False})
        touch.detach()
        page.wait_for_timeout(300)  # Let the touch fling finish before testing reading position.
    log.evaluate("node => { node.scrollTop = 0; }")
    messages.append({"id": 61, "sequence": 61, "role": "user", "text": "New message"})
    page.wait_for_function("document.querySelectorAll('.chat-message').length === 61")
    assert log.evaluate("node => node.scrollTop") == 0, "Polling displaced history reader"
    page.evaluate("Telegram.WebApp.testHeight = 320; Telegram.WebApp.viewportChanged()")
    layout()
    page.evaluate("Telegram.WebApp.testHeight = 0; Telegram.WebApp.viewportChanged()")
    page.set_viewport_size({"width": width, "height": 380})
    page.wait_for_function("document.body.getBoundingClientRect().height === 380")
    layout()
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_function(f"document.body.getBoundingClientRect().height === {height}")
    layout()
    (ROOT / ".artifacts").mkdir(exist_ok=True)
    page.screenshot(path=str(ROOT / f".artifacts/operator-scroll-{width}.png"))
    if width <= 760:
        page.locator("[data-back]").click()
    page.locator('[data-filter="others"]').click()
    inbox = page.locator("[data-inbox]")
    page.wait_for_function("document.querySelectorAll('.operator-row').length === 40")
    inbox.hover()
    page.mouse.wheel(0, 500)
    page.wait_for_function("document.querySelector('[data-inbox]').scrollTop > 100")
    # Background polling must not reset the operator's place in a long inbox.
    inbox.evaluate("node => { node.scrollTop = 250; }")
    page.wait_for_timeout(3300)
    assert inbox.evaluate("node => node.scrollTop") == 250, "Inbox refresh reset scroll"
    assert not errors, errors
    page.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        for width, height, lang in [
            (500, 790, "uz_latn"),
            (390, 700, "uz_cyrl"),
            (320, 568, "ru"),
            (1280, 800, "uz_latn"),
        ]:
            check(browser, width, height, lang)
        browser.close()
    print(
        {
            "ok": True,
            "checks": [
                "long_thread",
                "wheel_scroll",
                "reader_position",
                "telegram_keyboard",
                "window_resize",
                "inbox_scroll",
            ],
        }
    )


if __name__ == "__main__":
    main()
