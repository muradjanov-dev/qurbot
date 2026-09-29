"""Browser QA for the compact Tezqur admin workspace on local staging only."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Page, sync_playwright

ADMIN_ID = "499990001"
PRODUCT_VIEWPORTS = ((1440, 1000), (768, 900), (390, 844), (320, 700))
LANGUAGES = ("uz_cyrl", "uz_latn", "ru")


def _no_horizontal_overflow(page: Page, width: int, lang: str) -> None:
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"), (
        width,
        lang,
        page.url,
    )


def _sign_in(context, base_url: str) -> None:
    response = context.request.post(base_url + "/auth/dev", form={"tg_id": ADMIN_ID})
    assert response.ok, f"Admin staging login failed: {response.status}"


def _assert_focus_and_filters(
    page: Page,
    preview,
    *,
    query: str,
    status: str,
    category: str,
    scroll_y: int,
    table_scroll: int | None,
) -> None:
    page.wait_for_function("!document.querySelector('[data-image-dialog]').open")
    assert preview.evaluate(
        "el => el === document.activeElement"
    ), "Focus did not return to thumbnail"
    assert page.locator('.admin-filter-bar [name="q"]').input_value() == query
    assert page.locator('.admin-filter-bar [name="status"]').input_value() == status
    assert page.locator('.admin-filter-bar [name="category_id"]').input_value() == category
    current_y = page.evaluate("window.scrollY")
    assert abs(current_y - scroll_y) <= 3, (current_y, scroll_y)
    if table_scroll is not None:
        current_table_scroll = page.locator(".admin-table-scroll").evaluate("el => el.scrollLeft")
        assert abs(current_table_scroll - table_scroll) <= 3, (current_table_scroll, table_scroll)


def _wait_eye_visible(page: Page) -> None:
    page.wait_for_function(
        "() => { const el=document.querySelector('.admin-image-eye'); "
        "return el && Number(getComputedStyle(el).opacity) > 0.9; }",
        timeout=1500,
    )


def _open_loaded_image(page: Page, preview) -> None:
    preview.click()
    dialog = page.locator("[data-image-dialog]")
    page.wait_for_function("document.querySelector('[data-image-dialog]').open")
    photo = dialog.locator("[data-image-full]")
    page.wait_for_function(
        "() => { const img = document.querySelector('[data-image-full]'); "
        "return img.complete && img.naturalWidth > 0 && !img.hidden; }",
        timeout=10000,
    )
    assert photo.is_visible()
    assert dialog.locator("[data-image-title]").text_content().strip()


def _dashboard_checks(page: Page, output: Path, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    response = page.goto("/manage")
    assert response is not None and response.ok
    page.locator(".admin-dashboard").wait_for()
    header = page.locator(".admin-topbar").bounding_box()
    heading = page.locator(".admin-page-heading").bounding_box()
    assert header and heading
    gap = heading["y"] - (header["y"] + header["height"])
    assert 0 <= gap < 65, f"Dashboard heading is {gap:.0f}px below the header at {width}px"
    cards = page.locator(".admin-stat-card")
    assert cards.count() == 4
    heights = [card.bounding_box()["height"] for card in cards.all()]
    assert max(heights) <= 120, f"Dashboard metric cards stretched: {heights}"
    assert page.locator(".admin-recent-orders, .admin-recent-empty").count() > 0
    _no_horizontal_overflow(page, width, "uz_cyrl")
    page.screenshot(path=str(output / f"dashboard-{width}x{height}.png"), full_page=True)


def _products_checks(
    browser,
    base_url: str,
    output: Path,
    width: int,
    height: int,
    language: str,
    errors: list[str],
) -> None:
    context = browser.new_context(
        base_url=base_url,
        viewport={"width": width, "height": height},
        color_scheme="dark",
        has_touch=width <= 768,
    )
    context.route("https://telegram.org/**", lambda route: route.abort())
    context.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
    _sign_in(context, base_url)
    context.request.get(f"/lang/{language}?next=/manage/products")
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(f"{language}/{width}: {error}"))
    response = page.goto("/manage/products?category_id=18&status=available")
    assert response is not None and response.ok, (language, width, page.url)
    previews = page.locator("[data-image-preview]")
    assert previews.count() > 0, f"No product photo thumbnails at {language}/{width}"
    _no_horizontal_overflow(page, width, language)

    preview = previews.first
    query = page.locator('.admin-filter-bar [name="q"]').input_value()
    status = page.locator('.admin-filter-bar [name="status"]').input_value()
    category = page.locator('.admin-filter-bar [name="category_id"]').input_value()
    page.evaluate("window.scrollTo(0, Math.min(220, document.body.scrollHeight))")
    preview.scroll_into_view_if_needed()
    table = page.locator(".admin-table-scroll")
    table.evaluate("el => { el.scrollLeft = Math.min(140, el.scrollWidth); }")
    scroll_y = page.evaluate("window.scrollY")
    table_scroll = table.evaluate("el => el.scrollLeft")

    eye_opacity = preview.locator(".admin-image-eye").evaluate(
        "el => Number(getComputedStyle(el).opacity)"
    )
    if width > 768:
        assert eye_opacity < 0.1, f"Eye is unexpectedly always visible at {width}px"
        preview.hover()
        _wait_eye_visible(page)
        hovered_opacity = preview.locator(".admin-image-eye").evaluate(
            "el => Number(getComputedStyle(el).opacity)"
        )
        assert hovered_opacity > 0.9, f"Thumbnail hover did not reveal the eye at {width}px"
        page.mouse.move(0, 0)
        # A real Tab key establishes keyboard modality before checking focus-visible.
        page.keyboard.press("Tab")
        preview.focus()
        assert preview.evaluate(
            "el => el.matches(':focus-visible')"
        ), "Thumbnail lacks keyboard focus styling"
        _wait_eye_visible(page)
        focused_opacity = preview.locator(".admin-image-eye").evaluate(
            "el => Number(getComputedStyle(el).opacity)"
        )
        assert focused_opacity > 0.9, f"Keyboard focus did not reveal the eye at {width}px"

    if width <= 768:
        # Touch uses a direct click, without depending on a hover state.
        preview.tap()
        page.wait_for_function("document.querySelector('[data-image-dialog]').open")
        assert page.locator("[data-image-full]").evaluate(
            "el => el.complete && el.naturalWidth > 0"
        )
        page.locator("[data-image-close]").tap()
        _assert_focus_and_filters(
            page,
            preview,
            query=query,
            status=status,
            category=category,
            scroll_y=scroll_y,
            table_scroll=None,
        )

    # Native dialog semantics, title/full image, Escape, and focus restoration.
    # Keyboard focus can scroll the page before the modal opens; snapshot the
    # actual position immediately before opening it.
    scroll_y = page.evaluate("window.scrollY")
    table_scroll = table.evaluate("el => el.scrollLeft")
    _open_loaded_image(page, preview)
    expected_title = preview.get_attribute("data-image-name") or ""
    assert page.locator("[data-image-title]").text_content().strip() == expected_title
    page.screenshot(path=str(output / f"products-{language}-{width}.png"), full_page=True)
    page.keyboard.press("Escape")
    _assert_focus_and_filters(
        page,
        preview,
        query=query,
        status=status,
        category=category,
        scroll_y=scroll_y,
        table_scroll=table_scroll,
    )

    # The close control restores focus to the exact opener as well.
    _open_loaded_image(page, preview)
    page.screenshot(path=str(output / f"modal-{language}-{width}.png"))
    page.locator("[data-image-close]").click()
    _assert_focus_and_filters(
        page,
        preview,
        query=query,
        status=status,
        category=category,
        scroll_y=scroll_y,
        table_scroll=table_scroll,
    )

    # Clicking the dialog backdrop closes it and restores the thumbnail focus.
    _open_loaded_image(page, preview)
    box = page.locator("[data-image-dialog]").bounding_box()
    assert box
    page.mouse.click(max(1, box["x"] - 3), max(1, box["y"] - 3))
    page.wait_for_function("!document.querySelector('[data-image-dialog]').open")
    _assert_focus_and_filters(
        page,
        preview,
        query=query,
        status=status,
        category=category,
        scroll_y=scroll_y,
        table_scroll=table_scroll,
    )

    # A missing image leaves a friendly error inside the dialog, not a broken page.
    missing_path = "/__admin_modal_image_missing__.png"
    page.route(
        f"**{missing_path}",
        lambda route: route.fulfill(status=404, body="not found", content_type="image/png"),
    )
    preview.evaluate("(el, path) => { el.dataset.imagePreview = path; }", missing_path)
    preview.click()
    page.locator("[data-image-dialog]").wait_for(state="visible")
    error_status = page.locator("[data-image-status]")
    page.wait_for_function(
        "() => { const node=document.querySelector('[data-image-status]'); "
        "return node && !node.hidden && node.textContent.trim() === node.dataset.error; }",
        timeout=5000,
    )
    page.keyboard.press("Escape")
    page.wait_for_function("!document.querySelector('[data-image-dialog]').open")
    assert error_status.text_content().strip()
    context.close()


def check(base_url: str) -> None:
    if urlsplit(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Admin workspace QA only targets isolated loopback staging")
    output = Path(".artifacts/admin-compact")
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)

        # Dashboard density and heading placement at both desktop sizes.
        context = browser.new_context(
            base_url=base_url,
            viewport={"width": 1440, "height": 1000},
            color_scheme="dark",
        )
        context.route("https://telegram.org/**", lambda route: route.abort())
        context.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
        _sign_in(context, base_url)
        context.request.get("/lang/uz_cyrl?next=/manage")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(f"dashboard: {error}"))
        for width, height in ((1440, 1000), (1720, 1280)):
            _dashboard_checks(page, output, width, height)
        context.close()

        # Product library interaction in all locales and compact viewport sizes.
        for language in ("uz_cyrl", "uz_latn", "ru"):
            for width, height in ((1440, 1000), *PRODUCT_VIEWPORTS[1:]):
                _products_checks(browser, base_url, output, width, height, language, errors)

        browser.close()
    assert not errors, errors
    print("PASS: compact admin dashboard and image preview across locales and viewports")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18081")
    check(parser.parse_args().base_url)
