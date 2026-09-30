"""Browser checks for the operator inbox using the shipped JavaScript and DOM."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from jinja2 import Environment, FileSystemLoader

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except ImportError:  # pragma: no cover - optional local browser dependency
    sync_playwright = None  # type: ignore[assignment]

from app.core.config import settings
from app.core.i18n import t
from app.web.storefront.deps import ASSET_VERSION

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app/web/storefront/templates"
STATIC = ROOT / "app/web/storefront/static"

API_FIXTURE = r"""
(() => {
  window.Telegram = window.Telegram || {WebApp: {
    viewportHeight: window.innerHeight,
    onEvent(name, callback) { this[name] = callback; }, ready() {}, expand() {},
  }};
  const requests = [];
  const pending = new Map();
  const pendingSends = new Map();
  let nextCall = 1;
  let latestSequence = 30;
  let delayNextSend = false;
  let readCalls = 0;
  const row = (id, name = `Customer ${id}`, status = 'waiting', mine = false) => ({
    id, user_id: id + 1000, status, operator_id: mine ? 7 : null, mine,
    name, preview: `Latest preview from ${name}`, unread: 2,
    updated_at: '2026-09-30T10:15:00+00:00',
  });
  const response = (data, status = 200) => ({ok: status < 400, status, json: async () => data});
  const transcript = (id, after) => ({
    id, conversation_id: id, status: id === 42 ? 'human' : 'waiting',
    operator_id: id === 42 ? 7 : null,
    messages: Array.from({length: Math.max(0, latestSequence - after)}, (_, index) => {
      const sequence = after + index + 1;
      return {id: sequence, sequence, role: sequence % 2 ? 'user' : 'assistant',
        text: `Message ${sequence}. ${'Long reply text for a readable scroll area. '.repeat(2)}`};
    }),
    next_sequence: latestSequence,
  });
  function payload(call) {
    const url = new URL(call.url, location.href);
    if (url.pathname === '/api/chat/operator') {
      const q = url.searchParams.get('q') || '';
      const after = Number(url.searchParams.get('after_id') || 0);
      if (q === 'old') {
        return new Promise(resolve => pending.set(call.id, () => resolve(response({
          conversations: [row(9, 'Old delayed result')], next_cursor: null,
        }))));
      }
      if (q === 'fail') return response({error: 'fixture failure'}, 503);
      if (q === 'empty') return {conversations: [], next_cursor: null};
      if (q === 'latest') return {conversations: [row(8, 'Latest result')], next_cursor: null};
      if (q === 'tile' && url.searchParams.get('scope') === 'mine') {
        return {conversations: [row(42, 'Assigned customer', 'human', true)], next_cursor: null};
      }
      if (q === 'tile') {
        if (after === 0) return {
          conversations: Array.from(
            {length: 50}, (_, index) => row(index + 1, `Tile customer ${index + 1}`),
          ),
          next_cursor: 50,
        };
        return {conversations: [row(51, 'Tile customer 51')], next_cursor: null};
      }
      if (url.searchParams.get('scope') === 'mine') return {
        conversations: [row(42, 'Assigned customer', 'human', true)], next_cursor: null,
      };
      return {
        conversations: [row(42, 'Assigned customer', 'human', true), row(43)],
        next_cursor: null,
      };
    }
    const match = url.pathname.match(/^\/api\/chat\/operator\/(\d+)(?:\/(.*))?$/);
    if (!match) return {ok: true};
    const id = Number(match[1]);
    const action = match[2] || '';
    if (!action) return transcript(id, Number(url.searchParams.get('after') || 0));
    if (action === 'sales-requests') return {requests: []};
    if (action === 'read') { readCalls++; return {ok: true}; }
    if (action === 'claim') return {id, status: 'human', operator_id: 7, messages: []};
    if (action === 'close') return {ok: true};
    if (action === 'messages') {
      if (delayNextSend) {
        delayNextSend = false;
        return new Promise(resolve => pendingSends.set(call.id, () => {
          latestSequence++;
          resolve({ok: true});
        }));
      }
      latestSequence++;
      return {ok: true};
    }
    return {ok: true};
  }
  window.__operatorApiCalls = requests;
  window.__operatorReadCalls = () => readCalls;
  window.__appendCustomerMessage = () => { latestSequence++; };
  window.__setConversationLength = count => { latestSequence = count; };
  window.__delayNextOperatorSend = () => { delayNextSend = true; };
  window.__releaseOperatorSend = id => {
    const release = pendingSends.get(id);
    if (release) { pendingSends.delete(id); release(); }
  };
  window.__releaseOperatorApi = id => {
    const release = pending.get(id);
    if (release) { pending.delete(id); release(); }
  };
  window.fetch = (input, init = {}) => {
    const call = {
      id: nextCall++, url: String(input), method: init.method || 'GET', body: init.body || null,
    };
    requests.push(call);
    return Promise.resolve(payload(call)).then(value => {
      return value && typeof value.json === 'function' ? value : response(value);
    });
  };
})();
"""


def operator_html(lang: str = "uz_latn") -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True)
    env.globals.update(
        t=t,
        csrf_token=lambda request: "browser-test-csrf",
        asset_version=ASSET_VERSION,
        settings=settings,
    )
    user = SimpleNamespace(id=7, tg_id=7, full_name="Tezqur admin", username="operator")
    return env.get_template("operator.html").render(
        user=user,
        lang=lang,
        path="/operator",
        static_url="/static/store",
        js_messages={},
        store_ui_messages={},
        admin_ui_messages={},
        request=None,
        is_admin=True,
        admin_surface=True,
        admin_active="chats",
        flash=None,
    )


def launch_browser() -> tuple[object, Browser]:
    if sync_playwright is None:
        pytest.skip("Playwright is required for operator browser checks")
    playwright = sync_playwright().start()
    try:
        executable = os.environ.get("QURBOT_BROWSER_EXECUTABLE")
        if executable:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
        else:
            browser = playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host browser setup varies
        if not os.environ.get("QURBOT_BROWSER_EXECUTABLE") and sys.platform.startswith("linux"):
            system_chrome = shutil.which("google-chrome") or shutil.which("chromium")
            if system_chrome:
                try:
                    browser = playwright.chromium.launch(
                        executable_path=system_chrome, headless=True
                    )
                    return playwright, browser
                except Exception:
                    pass
        playwright.stop()
        pytest.skip(f"Chromium could not start: {exc}")
    return playwright, browser


def open_operator(page: Page, conversation: int | None = None) -> None:
    html = operator_html()

    def route(request_route) -> None:
        url = urlsplit(request_route.request.url)
        if url.netloc != "operator.test":
            request_route.fulfill(status=204, body="")
            return
        if url.path == "/operator":
            request_route.fulfill(body=html, content_type="text/html")
            return
        if url.path.startswith("/static/store/"):
            asset = STATIC / url.path.rsplit("/", 1)[-1]
            if asset.is_file():
                request_route.fulfill(path=str(asset))
                return
        request_route.fulfill(status=200, body="")

    page.route("**/*", route)
    page.add_init_script(API_FIXTURE)
    suffix = f"?conversation={conversation}" if conversation else ""
    page.goto(f"https://operator.test/operator{suffix}")
    page.wait_for_function(
        "Array.from(document.styleSheets).some(sheet => sheet.href?.includes('/operator.css'))"
    )
    page.wait_for_function(
        "window.__operatorApiCalls?.some(call => call.url.includes('/api/chat/operator'))"
    )
    page.wait_for_function("document.querySelector('[data-inbox]')?.children.length > 0")


@pytest.fixture
def browser_page():
    playwright, browser = launch_browser()
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(3000)
        yield page
    finally:
        browser.close()
        playwright.stop()


def test_search_debounces_and_late_results_cannot_replace_newer_query(browser_page: Page) -> None:
    page = browser_page
    open_operator(page)
    page.clock.install()
    search = page.get_by_role("searchbox")

    search.fill("o")
    page.clock.fast_forward(100)
    search.fill("ol")
    page.clock.fast_forward(100)
    search.fill("old")
    page.clock.fast_forward(299)
    assert [
        new_url_query(call["url"]).get("q")
        for call in page.evaluate("window.__operatorApiCalls")
        if new_url_query(call["url"]).get("q")
    ] == []
    page.clock.fast_forward(1)
    old_calls = [
        call
        for call in page.evaluate("window.__operatorApiCalls")
        if new_url_query(call["url"]).get("q") == "old"
    ]
    assert len(old_calls) == 1
    old_id = old_calls[0]["id"]

    search.fill("l")
    page.clock.fast_forward(100)
    search.fill("la")
    page.clock.fast_forward(100)
    search.fill("latest")
    page.clock.fast_forward(299)
    search_queries = [
        new_url_query(call["url"]).get("q")
        for call in page.evaluate("window.__operatorApiCalls")
        if new_url_query(call["url"]).get("q")
    ]
    assert search_queries == ["old"]
    page.clock.fast_forward(1)
    page.get_by_role("button", name="Latest result").wait_for()
    page.evaluate("id => window.__releaseOperatorApi(id)", old_id)
    page.wait_for_timeout(80)
    assert page.get_by_role("button", name="Latest result").count() == 1
    assert page.get_by_role("button", name="Old delayed result").count() == 0
    filtered = [
        call
        for call in page.evaluate("window.__operatorApiCalls")
        if new_url_query(call["url"]).get("q") in {"old", "latest"}
    ]
    assert [new_url_query(call["url"]).get("q") for call in filtered] == ["old", "latest"]


def test_search_shows_empty_and_error_states(browser_page: Page) -> None:
    page = browser_page
    open_operator(page)
    search = page.get_by_role("searchbox")
    search.fill("empty")
    page.wait_for_timeout(360)
    assert page.get_by_text("Mos murojaat topilmadi").is_visible()
    search.fill("fail")
    page.wait_for_timeout(360)
    assert page.get_by_text("Murojaatlarni yuklab bo‘lmadi").is_visible()
    assert page.get_by_role("button", name="Qayta urinib ko‘rish").is_visible()


def test_pagination_keeps_query_and_selected_filter(browser_page: Page) -> None:
    page = browser_page
    open_operator(page)
    page.get_by_role("searchbox").fill("tile")
    page.wait_for_timeout(360)
    page.locator('[data-conversation-id="1"]').wait_for()
    page.get_by_role("button", name="Yana ko'rsatish").click()
    page.locator('[data-conversation-id="51"]').wait_for()
    page.get_by_role("button", name="Mening suhbatlarim").click()
    page.get_by_role("button", name="Assigned customer").wait_for()
    requests = page.evaluate("window.__operatorApiCalls")
    tile_pages = [
        new_url_query(call["url"])
        for call in requests
        if new_url_path(call["url"]) == "/api/chat/operator"
        and new_url_query(call["url"]).get("q") == "tile"
    ]
    assert any(
        params.get("after_id") == "50" and params.get("scope") == "waiting" for params in tile_pages
    )
    mine_page = next(params for params in reversed(tile_pages) if params.get("scope") == "mine")
    assert mine_page["q"] == "tile"


def test_deep_link_read_visibility_and_mobile_draft(browser_page: Page) -> None:
    page = browser_page
    page.set_viewport_size({"width": 390, "height": 700})
    open_operator(page, conversation=42)
    page.wait_for_function(
        "document.querySelectorAll('[data-thread-log] .chat-message').length === 30"
    )
    assert page.locator("[data-operator]").get_attribute("class").find("thread-open") >= 0
    page.wait_for_function("window.__operatorReadCalls() === 1")
    page.evaluate("Telegram.WebApp.viewportHeight = 320; Telegram.WebApp.viewportChanged()")
    page.wait_for_function(
        "document.querySelector('[data-operator]').getBoundingClientRect().bottom <= 321"
    )
    assert page.locator(".admin-nav").is_hidden()
    assert (
        page.locator("[data-operator-form]").bounding_box()["y"]
        + page.locator("[data-operator-form]").bounding_box()["height"]
        <= 321
    )
    page.evaluate("Telegram.WebApp.viewportHeight = 0; Telegram.WebApp.viewportChanged()")
    log = page.locator("[data-thread-log]")
    log.evaluate("node => { node.scrollTop = 0; }")
    page.evaluate("window.__appendCustomerMessage()")
    page.wait_for_function(
        "document.querySelectorAll('[data-thread-log] .chat-message').length === 31"
    )
    jump = page.locator("[data-jump-latest]")
    assert jump.is_visible()
    assert page.evaluate("window.__operatorReadCalls()") == 1
    jump.click()
    page.wait_for_function("window.__operatorReadCalls() === 2")
    composer = page.locator('[data-operator-form] textarea[name="message"]')
    composer.fill("Draft for later")
    page.locator("[data-back]").click()
    page.wait_for_function(
        "!document.querySelector('[data-operator]').classList.contains('thread-open')"
    )
    assert (
        page.locator('[data-operator-form] textarea[name="message"]').input_value()
        == "Draft for later"
    )
    read_before = page.evaluate("window.__operatorReadCalls()")
    page.wait_for_timeout(3200)
    assert page.evaluate("window.__operatorReadCalls()") == read_before
    page.locator('[data-conversation-id="42"]').click()
    assert (
        page.locator('[data-operator-form] textarea[name="message"]').input_value()
        == "Draft for later"
    )


def test_read_waits_until_all_transcript_pages_are_loaded(browser_page: Page) -> None:
    page = browser_page
    open_operator(page)
    page.evaluate("window.__setConversationLength(100)")
    page.locator('[data-conversation-id="42"]').click()
    page.wait_for_function(
        "document.querySelectorAll('[data-thread-log] .chat-message').length === 100"
    )
    assert page.evaluate("window.__operatorReadCalls()") == 0
    page.evaluate("window.__setConversationLength(101)")
    page.wait_for_function(
        "document.querySelectorAll('[data-thread-log] .chat-message').length === 101", timeout=6000
    )
    page.wait_for_function("window.__operatorReadCalls() === 1", timeout=3000)


def test_hidden_page_and_in_flight_send_do_not_mark_unread(browser_page: Page) -> None:
    page = browser_page
    open_operator(page)
    page.evaluate(
        "Object.defineProperty(document, 'hidden', {configurable: true, get: () => true})"
    )
    page.locator('[data-conversation-id="42"]').click()
    page.wait_for_function(
        "document.querySelectorAll('[data-thread-log] .chat-message').length === 30"
    )
    assert page.evaluate("window.__operatorReadCalls()") == 0
    page.evaluate(
        "Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});\n"
        "document.dispatchEvent(new Event('visibilitychange'))"
    )
    page.wait_for_function("window.__operatorReadCalls() === 1")
    page.evaluate("window.__delayNextOperatorSend()")
    composer = page.locator('[data-operator-form] textarea[name="message"]')
    composer.fill("A reply while a new customer message arrives")
    page.locator('[data-operator-form] button[type="submit"]').click()
    page.wait_for_function(
        "window.__operatorApiCalls.some(call => "
        "call.method === 'POST' && call.url.endsWith('/messages'))"
    )
    send_id = page.evaluate(
        "window.__operatorApiCalls.find(call => "
        "call.method === 'POST' && call.url.endsWith('/messages')).id"
    )
    page.evaluate("window.__appendCustomerMessage()")
    page.wait_for_function(
        "document.querySelectorAll('[data-thread-log] .chat-message').length === 31", timeout=6000
    )
    assert page.evaluate("window.__operatorReadCalls()") == 1
    page.evaluate("id => window.__releaseOperatorSend(id)", send_id)
    page.wait_for_function("window.__operatorReadCalls() === 2")


def new_url_query(url: str) -> dict[str, str]:
    from urllib.parse import parse_qs

    return {key: values[-1] for key, values in parse_qs(urlsplit(url).query).items()}


def new_url_path(url: str) -> str:
    return urlsplit(url).path


@pytest.mark.parametrize(
    ("lang", "search_label", "retry_label"),
    [
        ("uz_latn", "Ism, username yoki ID bo‘yicha qidiring", "Qayta urinib ko‘rish"),
        ("uz_cyrl", "Исм, username ёки ID бўйича қидиринг", "Қайта уриниб кўриш"),
        ("ru", "Поиск по имени, username или ID", "Повторить"),
    ],
)
def test_operator_controls_use_the_saved_language(
    lang: str, search_label: str, retry_label: str
) -> None:
    html = operator_html(lang)
    assert f'placeholder="{search_label}"' in html
    assert retry_label in html
