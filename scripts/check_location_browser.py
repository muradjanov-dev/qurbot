"""Offline mobile browser and Telegram pin selection through the shipped JavaScript."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import Browser, Route, sync_playwright

from app.core.i18n import t

ROOT = Path(__file__).resolve().parents[1]
ENV = Environment(loader=FileSystemLoader(ROOT / "app/web/storefront/templates"), autoescape=True)
ENV.globals["t"] = t


def check(browser: Browser, mode: str) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 760})
    if mode == "telegram":
        page.add_init_script(
            """window.Telegram = {WebApp: {isVersionAtLeast: () => true,
            LocationManager: {init: cb => cb(),
            getLocation: cb => cb({latitude: 41.25, longitude: 69.20})}}};"""
        )
    elif mode == "browser":
        page.add_init_script(
            """Object.defineProperty(navigator, 'geolocation', {value: {
            getCurrentPosition: ok => ok({coords: {latitude: 41.25, longitude: 69.20}})}});"""
        )
    else:
        page.add_init_script(
            """Object.defineProperty(navigator, 'geolocation', {value: {
            getCurrentPosition: (ok, fail) => fail({code: 1})}});"""
        )
    html = '<form data-location-picker data-default-lat="41.31" data-default-lng="69.28" '
    html += 'data-tile-url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" '
    html += 'data-tile-attribution="OpenStreetMap">'
    html += '<input data-address-text name="address_text"><select data-district>'
    html += '<option value="">—</option>'
    html += '<option value="1">Test district</option></select>'
    html += ENV.get_template("location_picker.html").render(lang="uz_latn")
    html += '</form><script src="/leaflet.js"></script><script src="/location.js"></script>'

    def route(request: Route) -> None:
        path = urlsplit(request.request.url).path
        if path == "/":
            request.fulfill(body=html, content_type="text/html")
        elif path in {"/leaflet.js", "/location.js"}:
            request.fulfill(path=str(ROOT / "app/web/storefront/static" / path[1:]))
        elif path == "/api/geocode":
            request.fulfill(json={"ok": True, "address": "Test street 12", "district_id": 1})
        else:
            request.abort()

    page.route("**/*", route)
    page.goto("https://location.test/")
    page.locator("[data-location-current]").click()
    if mode == "denied":
        assert page.locator("[data-lat]").input_value() == ""
        assert page.locator("[data-location-status]").inner_text() == t("web_location_failed")
    else:
        page.wait_for_function("document.querySelector('[data-lat]').value === '41.25'")
        page.wait_for_function(
            "document.querySelector('[data-address-text]').value === 'Test street 12'"
        )
        assert page.locator("[data-address-text]").input_value() == "Test street 12"
    page.locator("[data-location-map-toggle]").click()
    page.locator("[data-location-map]").click(position={"x": 110, "y": 110})
    page.wait_for_function("document.querySelector('[data-lat]').value !== ''")
    assert page.locator("[data-lng]").input_value()
    page.close()
    print(mode, "passed")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        for mode in ("browser", "telegram", "denied"):
            check(browser, mode)
        browser.close()


if __name__ == "__main__":
    main()
