"""Staging-only mobile enquiry lifecycle using actual HTTP, not paid AI."""

import json
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:28081"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        customer_context = browser.new_context(viewport={"width": 390, "height": 760})
        customer_context.route("https://telegram.org/**", lambda route: route.abort())
        customer = customer_context.new_page()
        errors = []
        customer.on("pageerror", lambda e: errors.append(str(e)))
        for product_id in [8, 314, 315]:  # Read-only verified staging catalog IDs.
            customer.goto(BASE + f"/product/{product_id}")
            customer.locator("[data-add-product]").wait_for()
            customer.locator("[data-qty] input").fill("155")
            customer.locator("[data-add-product]").click()
            try:
                customer.wait_for_function(
                    "document.querySelector('[data-product-added]').textContent.includes('155')"
                )
            except PlaywrightTimeout as exc:
                raise AssertionError(
                    {
                        "product_id": product_id,
                        "quantity": customer.locator("[data-qty] input").input_value(),
                        "feedback": customer.locator("[data-product-added]").text_content(),
                        "toast": customer.locator("[data-toast]").text_content(),
                        "errors": errors,
                    }
                ) from exc
        customer.locator('a[href="/chat?cart=1"]').click()
        customer.locator("[data-cart-dialog]").wait_for(state="visible")
        customer.wait_for_function("document.querySelectorAll('.sales-cart-line').length === 3")
        assert customer.locator("[data-request-hint]").is_visible()
        qty = customer.locator(".sales-cart-line input").first
        with customer.expect_response(
            lambda response: "/api/cart/items/" in response.url and response.request.method == "PUT"
        ) as changed:
            qty.fill("160")
            qty.press("Tab")
        assert changed.value.status == 200, changed.value.text()
        assert changed.value.json()["lines"][0]["qty"] == "160"
        customer.wait_for_function("!document.querySelector('[data-checkout-submit]').disabled")
        customer.locator("[data-close-cart]").click()
        customer.locator("[data-open-cart]").click()
        customer.wait_for_function(
            "document.querySelector('.sales-cart-line input').value === '160'"
        )
        customer.locator('[name="name"]').fill("STAGING guided sales customer")
        customer.locator('[name="phone"]').fill("+998900000000")
        customer.locator('[name="district"]').select_option(index=1)
        customer.locator('[name="address"]').fill("STAGING synthetic address 155")
        customer.locator("[data-checkout-submit]").click()
        customer.locator('[data-checkout-status] a[href^="/sales-requests#"]').wait_for()
        data = customer_context.request.get(BASE + "/api/sales-requests").json()["requests"][0]
        assert len(data["items"]) == 3 and data["status"] == "open"
        assert data["items"][0]["qty"] == "160", data
        request_id, conversation_id = data["id"], data["conversation_id"]
        assert not customer_context.request.get(BASE + "/api/cart").json()["lines"]
        customer.locator("[data-checkout-status] a").click()
        assert customer.locator(f"#request-{request_id}").is_visible()

        admin_context = browser.new_context(viewport={"width": 390, "height": 760})
        admin_context.route("https://telegram.org/**", lambda route: route.abort())
        admin_context.request.post(
            BASE + "/auth/dev?next=/operator",
            form={"tg_id": "-99200920", "full_name": "STAGING browser operator"},
        )
        admin = admin_context.new_page()
        admin.on("pageerror", lambda e: errors.append(str(e)))
        admin.goto(BASE + f"/operator?conversation={conversation_id}")
        admin.locator("[data-claim]").click()
        note = admin.locator("[data-sales-requests] textarea")
        note.wait_for()
        assert admin.locator("[data-finish]").is_disabled()
        note.fill("STAGING agreed; no payment or warehouse task")
        # Polling must not erase an operator's draft or steal scroll.
        admin.wait_for_timeout(3500)
        assert "STAGING agreed" in note.input_value()
        admin.locator("[data-sales-requests] button").first.click()
        admin.wait_for_function("!document.querySelector('[data-finish]').disabled")
        Path(".artifacts").mkdir(exist_ok=True)
        admin.screenshot(path=".artifacts/sales-request-operator-mobile.png")
        admin.once("dialog", lambda dialog: dialog.accept())
        admin.locator("[data-finish]").click()
        customer.reload()
        assert "Kelishildi" in customer.locator(f"#request-{request_id}").inner_text()
        customer.screenshot(path=".artifacts/sales-request-customer-mobile.png")
        assert not errors, errors
        browser.close()
        print(
            json.dumps(
                {
                    "ok": True,
                    "request_id": request_id,
                    "checks": [
                        "three_variants",
                        "custom_155",
                        "edit_160",
                        "cart_reopen",
                        "one_request",
                        "operator_claim",
                        "close_blocked",
                        "draft_retained",
                        "resolve",
                        "customer_history",
                    ],
                }
            )
        )


if __name__ == "__main__":
    main()
