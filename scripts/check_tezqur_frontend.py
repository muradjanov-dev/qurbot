"""Exercise the real Tezqur pages on isolated staging; no production writes."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def check(base_url: str, roles: tuple[str, ...] = ("guest", "customer", "admin")) -> None:
    if urlsplit(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only isolated loopback staging is allowed")
    output = Path(".artifacts/tezqur-frontend")
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    checked = 0
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        for width, height in ((1440, 1000), (390, 844), (320, 680)):
            for role, telegram_id in (
                ("guest", None),
                ("customer", "499990002"),
                ("admin", "499990001"),
            ):
                if role not in roles:
                    continue
                context = browser.new_context(
                    base_url=base_url,
                    viewport={"width": width, "height": height},
                    color_scheme="dark",
                )
                context.route("https://telegram.org/**", lambda route: route.abort())
                context.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
                if telegram_id:
                    login = context.request.post("/auth/dev", form={"tg_id": telegram_id})
                    assert login.ok, login.text()
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                manage = page.goto("/manage")
                assert manage is not None
                if role == "guest":
                    assert "/login" in page.url, page.url
                elif role == "customer":
                    assert manage.status == 403
                    assert '"detail"' not in page.locator("body").inner_text()
                else:
                    assert manage.ok
                    assert page.locator(".admin-nav > a").count() == 6
                    assert page.locator('.admin-nav a[href="/manage/products"]').count() == 1
                routes = ["/catalog/all", "/chat", "/basket", "/account"]
                if role == "admin":
                    routes += [
                        "/manage",
                        "/manage/products",
                        "/manage/products/new",
                        "/manage/settings",
                        "/manage/settings/currency",
                    ]
                for language in ("uz_cyrl", "uz_latn", "ru"):
                    context.request.get(f"/lang/{language}?next=/catalog/all")
                    for route in routes:
                        response = page.goto(route)
                        assert response is not None and response.ok, (role, route, page.url)
                        page.wait_for_load_state("domcontentloaded")
                        assert (
                            page.locator('meta[name="color-scheme"]').get_attribute("content")
                            == "light"
                        )
                        assert "QurBot" not in page.title(), (route, page.title())
                        assert page.locator("[data-design-variant], [data-prototype]").count() == 0
                        overflow = page.evaluate(
                            "document.documentElement.scrollWidth > window.innerWidth + 2"
                        )
                        assert not overflow, (width, role, language, route, "horizontal overflow")
                        if role == "guest" and route == "/catalog/all":
                            assert page.locator("[data-telegram-login]").is_visible()
                        if language == "uz_cyrl" and role in {"admin", "guest"}:
                            name = route.strip("/").replace("/", "-") or "home"
                            page.screenshot(path=str(output / f"{role}-{width}-{name}.png"))
                        if route == "/chat" and language == "uz_cyrl" and width < 800:
                            composer = page.locator("[data-chat-form] textarea")
                            page.wait_for_function(
                                "!document.querySelector('[data-chat-form] textarea').disabled",
                                timeout=8000,
                            )
                            composer.fill("Viewport QA — do not send")
                            page.set_viewport_size({"width": width, "height": 380})
                            page.wait_for_timeout(120)
                            bounds = composer.bounding_box()
                            tabbar = page.locator(".tabbar").bounding_box()
                            assert bounds and tabbar
                            assert bounds["y"] >= 0 and bounds["height"] >= 40
                            assert bounds["y"] + bounds["height"] <= tabbar["y"] + 2
                            assert composer.input_value() == "Viewport QA — do not send"
                            page.set_viewport_size({"width": width, "height": height})
                        checked += 1
                context.close()
        browser.close()
    assert not errors, errors
    print(f"PASS: {checked} page/locale/role/viewport checks; no JS errors or horizontal overflow")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081")
    check(parser.parse_args().base_url)
