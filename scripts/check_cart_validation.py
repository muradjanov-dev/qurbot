"""Offline cart contact validation regression using real templates and JavaScript."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import Browser, Route, sync_playwright

from app.core.i18n import t

ROOT = Path(__file__).resolve().parents[1]


def check(browser: Browser, lang: str) -> None:
    env = Environment(
        loader=FileSystemLoader(ROOT / "app/web/storefront/templates"), autoescape=True
    )
    env.globals["t"] = t
    html = '<meta name="csrf-token" content="test"><button data-open-cart>Cart</button>'
    html += env.get_template("chat_cart.html").render(lang=lang, user=None)
    html += '<script src="/chat_cart.js"></script>'
    cart = {
        "revision": 1,
        "requires_confirmation": True,
        "lines": [
            {"canonical_id": 1, "canonical_name": "Test product", "qty": "1", "unit_code": "dona"}
        ],
    }
    posts = []
    page = browser.new_page()

    def route(r: Route) -> None:
        path = urlsplit(r.request.url).path
        if path == "/":
            r.fulfill(body=html, content_type="text/html")
        elif path == "/chat_cart.js":
            r.fulfill(path=str(ROOT / "app/web/storefront/static/chat_cart.js"))
        elif path == "/api/cart":
            r.fulfill(json=cart)
        elif path == "/api/checkout/options":
            r.fulfill(json={"districts": [{"id": 1, "name": "Test district"}]})
        elif path == "/api/sales-requests":
            posts.append(r.request.post_data_json)
            if len(posts) == 2:
                cart["lines"] = []
                r.fulfill(json={"ok": True, "request": {"id": 1}})
                return
            r.fulfill(
                status=422,
                json={"detail": [{"loc": ["body", "address_text"], "type": "string_too_short"}]},
            )
        else:
            r.abort()

    page.route("**/*", route)
    page.goto("https://cart.test/")
    page.locator("[data-open-cart]").click()
    page.wait_for_function("!document.querySelector('[data-checkout-submit]').disabled")
    page.locator("[name=name]").fill("Test User")
    page.locator("[name=phone]").fill("+998900000000")
    page.locator("[name=district]").select_option("1")
    page.locator("[name=address]").fill("Go")
    page.locator("[data-checkout-submit]").click()
    page.wait_for_timeout(150)
    assert not posts, "Short address was sent and received an opaque 422 error"
    assert page.locator("[name=address]").evaluate("e => !e.checkValidity()")
    page.locator("[name=address]").fill("     ")
    page.locator("[data-checkout-submit]").click()
    assert not posts, "Whitespace passed contact validation"
    page.locator("[name=address]").fill("Test street 10")
    page.locator("[data-checkout-submit]").click()
    page.wait_for_function(
        "document.querySelector('[data-checkout-status]').textContent.length > 0"
    )
    assert page.locator("[data-checkout-status]").inner_text() == t(
        "sales_address_invalid", lang=lang
    )
    assert not page.locator("[name=address]").is_disabled()
    page.locator("[name=address]").fill("Corrected street 12")
    page.locator("[data-checkout-submit]").click()
    page.locator('[data-checkout-status] a[href="/sales-requests#request-1"]').wait_for()
    assert len(posts) == 2 and posts[-1]["address_text"] == "Corrected street 12"
    assert (
        page.locator("[data-checkout-status] a").get_attribute("href")
        == "/sales-requests#request-1"
    )
    page.close()
    print(lang, "short address, whitespace, server rejection and editable retry passed")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        for lang in ("uz_latn", "uz_cyrl", "ru"):
            check(browser, lang)
        browser.close()


if __name__ == "__main__":
    main()
