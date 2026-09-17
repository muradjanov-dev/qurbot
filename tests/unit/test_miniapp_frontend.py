"""Exercise Mini App authentication with real frontend code in a Node VM."""

import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from app.core.i18n import t


def test_miniapp_navigation_recovery_and_server_verified_auth() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute storefront JavaScript")
    script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('app/web/storefront/static/app.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function page({init = '', stored = new Map(), authed = false, platform = 'android',
               next = '/orders', post = 'ok', cookie = true, storageError = false,
               pathname = '/login', redirect = next, unsafe = false} = {}) {
  const calls = [], navigations = [];
  const notice = {hidden: true,
    dataset: {missing: 'reopen /start', error: 'auth failed', loading: 'loading'}};
  const storage = {
    getItem(key) { if (storageError) throw Error('blocked'); return stored.get(key) || null; },
    setItem(key, value) { if (storageError) throw Error('blocked'); stored.set(key, value); },
    removeItem(key) { if (storageError) throw Error('blocked'); stored.delete(key); }
  };
  const sandbox = {
    window: {QB: {authed, i18n: {}}, Telegram: {WebApp: {initData: init,
      initDataUnsafe: unsafe ? {user: {id: 1}} : {}, platform, ready() {}, expand() {}}},
      location: {pathname, origin: 'https://shop.test', replace: url => navigations.push(url)}},
    document: {querySelector: selector => selector === '[data-telegram-auth]' ? notice
      : selector === '[data-login-next]' && pathname === '/login' ? {dataset: {loginNext: next}}
      : null, querySelectorAll: () => [], addEventListener() {}},
    sessionStorage: storage, localStorage: storage, URL, AbortController,
    setTimeout: () => 1, clearTimeout() {},
    fetch: async (url, options) => {
      calls.push({url, options});
      assert(!url.includes('signed-secret'));
      if (url === '/auth/webapp') {
        if (post === 'network') throw Error('network');
        if (post === 'pending') return new Promise(() => {});
        return {ok: post === 'ok', json: async () => ({ok: post === 'ok', redirect})};
      }
      assert.equal(url, '/api/cart');
      return {ok: cookie, json: async () => ({ok: cookie})};
    }
  };
  vm.runInNewContext(source, sandbox);
  return {calls, navigations, notice, stored};
}
(async () => {
  let p = page({unsafe: true}); await tick();
  assert.equal(p.calls.length, 0); assert.equal(p.notice.hidden, false);
  assert.match(p.notice.textContent, /reopen/); // Unsafe user data cannot authenticate.

  p = page({platform: 'unknown'}); await tick();
  assert.equal(p.calls.length, 0); assert.equal(p.notice.hidden, true);

  p = page({init: 'signed-secret', next: '/orders?tab=open'}); await tick();
  assert.deepEqual(p.navigations, ['/orders?tab=open']);
  assert.equal(JSON.parse(p.calls[0].options.body).next, '/orders?tab=open');
  assert.equal(JSON.parse(p.calls[0].options.body).init_data, 'signed-secret');
  assert.equal(p.calls[0].options.credentials, 'same-origin');
  assert(!p.stored.has('qb_telegram_init_data'));
  assert.equal(p.stored.get('qb_telegram_auth_attempted'), '1');

  let repeated = page({init: 'signed-secret', stored: p.stored}); await tick();
  assert.equal(repeated.calls.length, 0); assert.equal(repeated.navigations.length, 0);
  assert.equal(repeated.notice.textContent, 'auth failed');
  page({authed: true, stored: p.stored});
  assert.equal(p.stored.size, 0);

  p = page({init: 'signed-secret', cookie: false}); await tick();
  assert.equal(p.navigations.length, 0); assert.equal(p.notice.textContent, 'auth failed');
  repeated = page({init: 'signed-secret', stored: p.stored}); await tick();
  assert.equal(repeated.calls.length, 0); // Blocked cookies cannot start a reload loop.

  for (const post of ['rejected', 'network']) {
    p = page({init: 'signed-secret', post}); await tick();
    assert.equal(p.navigations.length, 0); assert.equal(p.notice.textContent, 'auth failed');
  }
  p = page({init: 'signed-secret', storageError: true}); await tick();
  assert.equal(p.calls.length, 0); assert.equal(p.notice.textContent, 'auth failed');

  p = page({init: 'signed-secret', pathname: '/catalog', post: 'pending'});
  assert.equal(p.stored.get('qb_telegram_init_data'), 'signed-secret');
  const navigated = page({stored: p.stored, next: '/chat'}); await tick();
  assert.equal(JSON.parse(navigated.calls[0].options.body).init_data, 'signed-secret');
  assert.deepEqual(navigated.navigations, ['/chat']);
  assert(!navigated.stored.has('qb_telegram_init_data'));

  for (const redirect of ['//evil.test', '/\\evil.test', '/login', 'https://evil.test']) {
    p = page({init: 'signed-secret', redirect}); await tick();
    assert.deepEqual(p.navigations, ['/']);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
@pytest.mark.parametrize("username", [None, "QurTestBot", "bad/path?x=bot"])
def test_login_recovery_is_visible_without_widget(lang: str, username: str | None) -> None:
    root = Path(__file__).resolve().parents[2]
    env = Environment(
        loader=FileSystemLoader(root / "app/web/storefront/templates"), autoescape=True
    )
    env.globals.update(t=t, csrf_token=lambda request: "")
    html = env.get_template("login.html").render(
        lang=lang,
        user=None,
        path="/login",
        static_url="/static/store",
        js_messages={},
        request=None,
        bot_username=username,
        next_url="/orders?tab=open",
    )
    assert t("web_auth_reopen", lang=lang).replace("'", "&#39;") in html
    assert 'data-login-next="/orders?tab=open"' in html
    assert "web_auth_" not in html
    assert ('href="https://t.me/QurTestBot?start=webapp"' in html) is (username == "QurTestBot")
    if username != "QurTestBot":
        assert 'href="https://t.me/' not in html
