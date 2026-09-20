"""Real-browser, real-worker staging test; no model calls or production users.

Prerequisites: staging with AI/Telegram delivery disabled, SSH tunnel on 28081,
and synthetic admin -99200920. Never point this at production.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:28081"
ARTIFACTS = Path(".artifacts")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        admin_context = browser.new_context(viewport={"width": 1280, "height": 850})
        admin_context.route("https://telegram.org/**", lambda route: route.abort())
        response = admin_context.request.post(
            BASE + "/auth/dev?next=/operator",
            form={"tg_id": "-99200920", "full_name": "STAGING browser operator"},
        )
        assert response.status == 200 and "data-operator" in response.text()
        admin = admin_context.new_page()
        errors = []
        admin.on("pageerror", lambda error: errors.append(str(error)))
        admin.goto(BASE + "/operator")

        guest_context = browser.new_context(viewport={"width": 390, "height": 760})
        guest_context.route("https://telegram.org/**", lambda route: route.abort())
        guest = guest_context.new_page()
        guest.on("pageerror", lambda error: errors.append(str(error)))
        guest.goto(BASE + "/")
        guest.locator(".hero a[href='/chat']").click()
        guest.wait_for_function("!document.querySelector('#chat-message').disabled")
        assert not guest.locator('a[href^="/login"]').count()
        guest.locator("#chat-message").fill("STAGING browser guest: fanera kerak")
        guest.locator("[data-chat-send]").click()
        guest.wait_for_function("document.querySelectorAll('.chat-message').length >= 2")
        snapshot = guest_context.request.get(BASE + "/api/chat").json()
        conversation_id = snapshot["conversation_id"]
        guest.locator(".chat-menu summary").click()
        guest.once("dialog", lambda dialog: dialog.accept())
        guest.locator("[data-chat-operator]").click()
        guest.wait_for_function(
            "document.querySelector('[data-chat-mode]').textContent.includes('Operator')"
        )
        admin.goto(BASE + f"/operator?conversation={conversation_id}")
        admin.locator("[data-claim]").wait_for(state="visible")
        admin.locator("[data-claim]").click()
        admin.wait_for_function("!document.querySelector('#operator-message').disabled")
        admin.locator("#operator-message").fill("STAGING operator: qalinligini ayting")
        admin.locator("[data-operator-form] button").click()
        guest.wait_for_function(
            "document.querySelector('[data-chat-log]').textContent.includes('qalinligini ayting')"
        )
        admin.screenshot(path=str(ARTIFACTS / "operator-desktop.png"))
        guest.screenshot(path=str(ARTIFACTS / "visitor-mobile.png"))
        admin.set_viewport_size({"width": 390, "height": 760})
        assert admin.locator("[data-thread-log]").is_visible()
        admin.screenshot(path=str(ARTIFACTS / "operator-mobile.png"))
        guest.locator("[data-open-cart]").click()
        assert guest.locator("[data-cart-dialog]").is_visible()
        guest.wait_for_function(
            "document.querySelector('[data-cart-lines]').textContent.length > 0"
        )
        guest.locator("[data-close-cart]").click()
        admin.once("dialog", lambda dialog: dialog.accept())
        admin.locator("[data-finish]").click()
        guest.wait_for_function(
            "document.querySelector('[data-chat-mode]').textContent.includes('AI yordamchi')"
        )
        assert not errors, errors
        guest.reload()
        guest.wait_for_function("!document.querySelector('#chat-message').disabled")
        assert "qalinligini ayting" in guest.locator("[data-chat-log]").inner_text()
        print(
            {
                "ok": True,
                "checks": [
                    "no_SDK_guest",
                    "worker",
                    "consent",
                    "operator_UI",
                    "reply",
                    "resume_AI",
                    "cart_dialog",
                    "cookie_history",
                    "mobile",
                ],
                "paid_AI": 0,
            }
        )
        browser.close()


if __name__ == "__main__":
    main()
