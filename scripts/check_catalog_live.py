"""Browser acceptance checks against an isolated local staging deployment.

The target must be loopback and expose staging-only /auth/dev. The two IDs
must be seeded as a staging admin/customer; no real Telegram APIs are used.
"""

from __future__ import annotations

import argparse
import base64
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import sync_playwright


def check(base_url: str, category_id: str) -> None:
    if urlsplit(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Browser acceptance checks require an isolated loopback target")
    output = Path(".artifacts/catalog-live")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        admin = browser.new_context(base_url=base_url, viewport={"width": 1280, "height": 900})
        customer = browser.new_context(base_url=base_url, viewport={"width": 390, "height": 844})
        errors: list[str] = []
        for context, user_id in ((admin, "499990001"), (customer, "499990002")):
            context.route("https://telegram.org/**", lambda route: route.abort())
            context.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
            result = context.request.post("/auth/dev", form={"tg_id": user_id})
            assert result.ok
        # A previous failed smoke run may have left archived fixture products
        # in this synthetic customer's cart. Reset only this local test account.
        page_html = customer.request.get("/chat").text()
        csrf = re.search(r'name="csrf-token" content="([^"]+)"', page_html).group(1)
        snapshot = customer.request.get("/api/cart").json()
        for line in list(snapshot["lines"]):
            removed = customer.request.delete(
                f"/api/cart/items/{line['canonical_id']}?expected_revision={snapshot['revision']}",
                headers={"X-CSRF-Token": csrf},
            )
            assert removed.ok, removed.text()
            snapshot = removed.json()
        manage = admin.new_page()
        client = customer.new_page()
        for page in (manage, client):
            page.on("pageerror", lambda error: errors.append(str(error)))
        unique = "Browser QA " + uuid4().hex[:8]
        manage.goto("/manage/products/new")
        manage.locator('[name="name"]').fill(unique)
        manage.locator('[name="name_uz_cyrl"]').fill(unique)
        manage.locator('[name="name_ru"]').fill(unique)
        manage.locator('[name="category_id"]').select_option(category_id)
        manage.locator('[name="unit_code"]').select_option("dona")
        manage.locator('[name="price"]').fill("100000")
        manage.locator('[name="stock_status"]').select_option("in_stock")
        manage.locator('button[type="submit"]').first.click()
        manage.wait_for_url("**/manage/products/*")
        product_id = manage.url.rstrip("/").rsplit("/", 1)[-1]
        assert product_id.isdigit(), manage.url
        assert manage.locator('[name="stock_qty"]').count() == 0
        client.goto(f"/product/{product_id}")
        qty = client.locator("[data-qty] input")
        qty.wait_for(state="visible")
        client.wait_for_function("!document.querySelector('[data-qty] input').disabled")
        qty.fill("27")
        product_form = manage.locator('form[action="/manage/products/' + product_id + '"]')
        product_form.locator('[name="name"]').fill(unique + " updated")
        product_form.locator('[name="name_uz_cyrl"]').fill(unique + " updated")
        product_form.locator('[name="name_ru"]').fill(unique + " updated")
        product_form.locator('button[type="submit"]').click()
        manage.wait_for_load_state("networkidle")
        client.get_by_role("heading", name=unique + " updated", exact=True).wait_for(timeout=7000)
        assert qty.input_value() == "27", "Live refresh reset the quantity"
        offer = manage.locator('form[action^="/manage/offers/"]').first
        offer.locator('[name="price"]').fill("125000")
        offer.locator('button[type="submit"]').click()
        client.wait_for_function(
            "document.querySelector('.price').textContent.includes('125.000')", timeout=7000
        )
        assert qty.input_value() == "27"
        # Keep a checkout open in a second customer tab while admin changes price.
        client.locator("[data-add-product]").click()
        client.wait_for_function(
            "document.querySelector('[data-product-added]').textContent.length > 0"
        )
        cart_page = customer.new_page()
        cart_page.on("pageerror", lambda error: errors.append(str(error)))
        cart_page.goto("/chat?cart=1")
        cart_page.locator("[data-cart-dialog]").wait_for(state="visible")
        checkout = cart_page.locator("[data-chat-checkout]")
        checkout.locator('[name="name"]').fill("Staging customer")
        checkout.locator('[name="phone"]').fill("+998901234567")
        checkout.locator('[name="district"]').select_option("1")
        checkout.locator('[name="address"]').fill("Staging address 12")
        checkout.locator("[data-checkout-submit]").click()
        cart_page.locator("[data-checkout-summary] strong").wait_for()
        offer = manage.locator('form[action^="/manage/offers/"]').first
        offer.locator('[name="price"]').fill("130000")
        offer.locator('button[type="submit"]').click()
        cart_page.wait_for_function(
            "document.querySelector('[data-checkout-summary]').children.length === 0", timeout=7000
        )
        assert checkout.locator('[name="address"]').input_value() == "Staging address 12"
        assert checkout.locator('[name="phone"]').input_value() == "+998901234567"
        assert cart_page.locator("[data-checkout-status]").text_content()
        cart_page.close()
        # A new image must replace the URL observed by an already open page.
        old_image = client.locator("img.thumb").get_attribute("src")
        product_form = manage.locator('form[action="/manage/products/' + product_id + '"]')
        product_form.locator('[name="photo"]').set_input_files(
            {
                "name": "qa.png",
                "mimeType": "image/png",
                "buffer": base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9GkZ4AAAAASUVORK5CYII="
                ),
            }
        )
        product_form.locator('button[type="submit"]').click()
        client.wait_for_function(
            "old => document.querySelector('img.thumb').getAttribute('src') !== old",
            arg=old_image,
            timeout=7000,
        )
        assert qty.input_value() == "27"
        client.screenshot(path=str(output / "customer.png"), full_page=True)
        manage.screenshot(path=str(output / "admin.png"), full_page=True)
        manage.once("dialog", lambda dialog: dialog.accept())
        manage.locator('form[action$="/archive"] button').click()
        client.wait_for_function(
            "document.querySelector('[data-live-root]').dataset.productActive === '0'", timeout=7000
        )
        assert client.locator("[data-add-product]").is_disabled()
        manage.goto(f"/manage/products/{product_id}")
        manage.locator('form[action$="/restore"] button').click()
        client.wait_for_function(
            "document.querySelector('[data-live-root]').dataset.productActive === '1'", timeout=7000
        )
        assert not client.locator("[data-add-product]").is_disabled()
        assert not errors, errors
        browser.close()
        print(
            "PASS: admin CRUD, live name/price/photo, retained quantity, "
            "archive/restore, no browser errors"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081")
    parser.add_argument("--category-id", required=True)
    args = parser.parse_args()
    started = time.monotonic()
    check(args.base_url, args.category_id)
    print(f"Browser acceptance completed in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main()
