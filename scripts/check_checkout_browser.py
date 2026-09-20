"""Offline real-browser checkout interaction with deterministic API fixtures."""

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from app.core.i18n import t

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(ROOT / "app/web/storefront/templates"), autoescape=True
    )
    env.globals.update(t=t, csrf_token=lambda request: "fixture", asset_version="checkout-test")
    html = env.get_template("chat.html").render(
        user=SimpleNamespace(id=1, tg_id=None, full_name=None),
        lang="uz_latn",
        path="/chat",
        js_messages={},
        static_url="/static/store",
        request=None,
    )
    cart = {
        "ok": True,
        "revision": 1,
        "lines": [
            {"canonical_id": 1, "qty": "2", "canonical_name": "Test fanera", "unit_code": "dona"}
        ],
    }
    variant = {
        "strategy": "CHEAPEST_TOTAL",
        "grand_total_raw": "25000",
        "grand_total": "25 000 UZS",
        "delivery_total": "5 000 UZS",
        "items": [{"name": "Test fanera", "qty": "2 dona", "cost": "20 000 UZS"}],
    }
    orders = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        page = browser.new_page(viewport={"width": 390, "height": 760})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(r):
            path = urlsplit(r.request.url).path
            if path.startswith("/static/store/"):
                r.fulfill(path=str(ROOT / "app/web/storefront/static" / path.split("/")[-1]))
            elif path == "/chat":
                r.fulfill(body=html, content_type="text/html")
            elif path == "/api/cart":
                r.fulfill(json=cart)
            elif path == "/api/chat":
                r.fulfill(json={"conversation_id": 1, "status": "ai", "messages": []})
            elif path == "/api/checkout/options":
                r.fulfill(json={"districts": [{"id": 1, "name": "Test tuman"}]})
            elif path == "/api/checkout/preview":
                r.fulfill(json={"ok": True, "variant": variant})
            elif path == "/api/order":
                body = r.request.post_data_json
                assert body["contact_name"] == "Test customer" and body["district_id"] == 1
                orders.append(body)
                if len(orders) == 1:
                    variant.update(grand_total_raw="27000", grand_total="27 000 UZS")
                    r.fulfill(
                        json={
                            "ok": False,
                            "price_changed": True,
                            "variant": variant,
                            "error": "Price changed",
                        }
                    )
                else:
                    assert body["expected_total"] == "27000"
                    assert body["idempotency_key"] != orders[0]["idempotency_key"]
                    cart.update(revision=2, lines=[])
                    r.fulfill(json={"ok": True, "order_id": 99})
            else:
                r.fulfill(body="", content_type="application/javascript")

        page.route("**/*", route)
        page.goto("https://fixture.test/chat")
        page.locator("[data-open-cart]").click()
        page.locator('[name="name"]').fill("Test customer")
        page.locator('[name="phone"]').fill("+998901234567")
        page.locator('[name="district"]').select_option("1")
        page.locator('[name="address"]').fill("Test street 12")
        page.locator("[data-checkout-submit]").click()
        page.wait_for_function(
            "document.querySelector('[data-checkout-summary]').textContent.includes('25 000')"
        )
        page.screenshot(path=str(ROOT / ".artifacts/checkout-mobile.png"))
        page.locator("[data-checkout-submit]").click()
        page.wait_for_function(
            "document.querySelector('[data-checkout-summary]').textContent.includes('27 000')"
        )
        assert len(orders) == 1
        page.locator("[data-checkout-submit]").click()
        page.wait_for_function(
            "document.querySelector('[data-checkout-status]').textContent.includes('#99')"
        )
        assert len(orders) == 2 and not errors, errors
        print(
            json.dumps(
                {
                    "ok": True,
                    "checks": [
                        "drawer",
                        "contact_form",
                        "quote",
                        "price_reconfirmation",
                        "order_success",
                    ],
                }
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
