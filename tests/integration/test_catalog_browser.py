"""Optional real-browser check for catalogue return position and narrow layouts.

Run with ``QURBOT_BROWSER_EXECUTABLE=/path/to/chrome-headless-shell pytest ...``.
The normal CI suite skips it when Playwright or Chromium is unavailable.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct
from tests.integration.test_storefront_web import _seed, client  # noqa: F401


@pytest.mark.asyncio
async def test_catalogue_return_and_layout_in_browser(
    request: pytest.FixtureRequest,
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storefront_client: TestClient = request.getfixturevalue("client")
    playwright = pytest.importorskip("playwright.async_api")
    executable = os.environ.get("QURBOT_BROWSER_EXECUTABLE")
    if not executable or not Path(executable).is_file():
        pytest.skip("Set QURBOT_BROWSER_EXECUTABLE to run the browser check")

    data = await _seed(test_session)
    test_session.add_all(
        CanonicalProduct(
            slug=f"browser-product-{index}",
            name_uz=f"Fanera berezovaya 2x4 {index} mm (1525x1525)",
            name_uz_cyrl=f"Фанера 2x4 {index} мм",
            name_ru=f"Фанера 2x4 {index} мм",
            category_id=data.category_id,
            base_unit_code="dona",
            search_doc=f"fanera {index}",
            reference_price=Decimal("10000"),
        )
        for index in range(1, 49)
    )
    await test_session.flush()
    monkeypatch.setattr(settings, "web_catalog_page_size", 24)

    async with playwright.async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=executable)
        page = await browser.new_page(viewport={"width": 390, "height": 720})

        async def serve(route: object) -> None:
            request = route.request  # type: ignore[attr-defined]
            parsed = urlsplit(request.url)
            path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            if parsed.path == "/static/store/session.js":
                await route.fulfill(  # type: ignore[attr-defined]
                    status=200,
                    content_type="application/javascript",
                    body="window.QB.ready = Promise.resolve(true);",
                )
            elif parsed.path == "/api/basket/product":
                await route.fulfill(  # type: ignore[attr-defined]
                    status=200,
                    content_type="application/json",
                    body='{"ok":true,"line":{"canonical_id":99,"canonical_name":"Fanera",'
                    '"qty":"1","unit_code":"dona","line_no":1}}',
                )
            elif parsed.path == "/telegram-web-app.js":
                await route.abort()  # type: ignore[attr-defined]
            else:
                response = storefront_client.get(path)
                await route.fulfill(  # type: ignore[attr-defined]
                    status=response.status_code,
                    body=response.content,
                    headers={"content-type": response.headers.get("content-type", "text/html")},
                )

        await page.route("https://telegram.org/**", lambda route: route.abort())
        await page.route("http://qurbot.test/**", serve)

        for listing in ("/catalog/all?page=2", f"/catalog/{data.category_id}?page=2"):
            for return_index in (0, 1):
                await page.goto("http://qurbot.test" + listing)
                await page.evaluate("window.scrollTo(0, 480)")
                await page.locator("[data-catalog-product]").nth(6).click()
                saved = await page.evaluate(
                    "Number(sessionStorage.getItem('qb_catalog_scroll:' + "
                    "new URLSearchParams(location.search).get('from')))"
                )
                assert saved > 100
                await page.locator("[data-add-product]").click()
                await page.wait_for_function(
                    "document.querySelector('[data-product-added]').textContent.includes('Fanera')"
                )
                await page.locator("[data-catalog-return]").nth(return_index).click()
                assert urlsplit(page.url).path + "?" + urlsplit(page.url).query == listing
                await page.wait_for_function("window.scrollY === " + str(saved))
                assert abs(await page.evaluate("window.scrollY") - saved) <= 3
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        for width in (768, 820, 1000, 1280):
            await page.set_viewport_size({"width": width, "height": 720})
            await page.goto("http://qurbot.test" + listing)
            await page.locator("[data-catalog-product]").nth(6).click()
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width

        await page.set_viewport_size({"width": 390, "height": 720})
        await page.evaluate(
            "sessionStorage.setItem('qb_catalog_scroll:/catalog/"
            + str(data.category_id)
            + "', '800')"
        )
        await page.goto(f"http://qurbot.test/product/{data.product_id}")
        await page.locator('a[href="/catalog/' + str(data.category_id) + '"]').first.click()
        assert await page.evaluate("window.scrollY") == 0
        await browser.close()
