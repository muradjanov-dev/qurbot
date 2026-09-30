"""Run legacy-cart recovery through the storefront's actual browser script."""

import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.guest_claim_i18n import GUEST_CLAIM_MESSAGES


def test_conflicting_local_cart_stays_visible_for_review() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute storefront JavaScript")
    root = Path(__file__).resolve().parents[2]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.handlers = {};
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = '';
    this._text = '';
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute(name, value) { this[name] = value; }
  querySelector(selector) { return this.selectors?.[selector] || null; }
  querySelectorAll(selector) {
    if (selector === 'input[data-drop-local-id]:checked') {
      return this.children.flatMap(child => child.querySelectorAll(selector));
    }
    if (selector === 'input[data-drop-local-id]:checked' &&
        this.dataset.dropLocalId !== undefined) {
      return this.checked ? [this] : [];
    }
    return this.children.flatMap(child => child.querySelectorAll(selector));
  }
}

const local = new Map([['qb_basket_v1', JSON.stringify([
  {canonical_id: 1, qty: '5', unit_code: 'dona', status: 'ok', canonical_name: 'Tile'}
])]]);
const session = new Map();
const storage = map => ({getItem: key => map.has(key) ? map.get(key) : null,
  setItem: (key, value) => map.set(key, String(value)), removeItem: key => map.delete(key)});
const card = new Element('div');
card.hidden = true;
card.dataset = {
  previewLoading: 'Loading',
  previewFailed: 'Saved items could not be combined. They are still here.'
};
const draftList = new Element('ul');
const message = new Element('p');
const retry = new Element('button');
const drop = new Element('button');
card.selectors = {
  '[data-local-cart-draft]': draftList,
  '[data-local-cart-message]': message,
  '[data-retry-local-cart]': retry,
  '[data-drop-local-cart]': drop
};
const documentHandlers = {};
const serverLines = [{canonical_id: 1, qty: '2', unit_code: 'qop', status: 'ok',
  canonical_name: 'Tile'}];
const sandbox = {
  window: {QB: {authed: true, lang: 'uz_latn', i18n: {}}, localStorage: storage(local)},
  document: {
    hidden: false,
    querySelector: selector => selector === 'meta[name="csrf-token"]' ? {content: 'csrf-test'}
      : selector === '[data-local-cart-review]' ? card : null,
    querySelectorAll: () => [],
    addEventListener: (name, handler) => { documentHandlers[name] = handler; },
    createElement: tag => new Element(tag),
    createTextNode: text => {
      const node = new Element('#text');
      node.textContent = text;
      return node;
    }
  },
  localStorage: storage(local),
  sessionStorage: storage(session),
  crypto: {randomUUID: () => 'stable-merge-id'},
  setTimeout,
  clearTimeout,
  fetch: async (url, options = {}) => {
    if (url === '/api/cart') {
      return {ok: true, json: async () => ({ok: true, revision: 7, lines: serverLines})};
    }
    if (url === '/api/cart/merge') {
      return {ok: false, json: async () => ({ok: false, code: 'unit_conflict',
        revision: 7, lines: serverLines})};
    }
    throw new Error('Unexpected request: ' + url + ' ' + options.method);
  }
};

const source = fs.readFileSync('app/web/storefront/static/app.js', 'utf8');
vm.runInNewContext(source, sandbox);
(async () => {
  await documentHandlers.DOMContentLoaded();
  assert.equal(card.hidden, false, 'the retained local draft should open its review card');
  assert.match(draftList.textContent, /Tile/);
  assert.match(draftList.textContent, /5 dona/);
  assert.equal(local.has('qb_basket_v1'), true, 'a failed merge must keep the saved draft');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", script], cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_cart_review_retry_discard_and_order_replay() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute storefront JavaScript")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, "tests/unit/legacy_cart_recovery.test.cjs"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_cart_review_copy_covers_all_storefront_languages() -> None:
    keys = {
        "legacy_cart_source_title",
        "legacy_cart_review_hint",
        "legacy_cart_drop_item",
        "legacy_cart_retry",
        "legacy_cart_drop_selected",
        "legacy_cart_retrying",
        "legacy_cart_review_failed",
        "legacy_cart_review_conflict",
        "legacy_cart_review_changed",
        "legacy_cart_discarded",
        "legacy_cart_storage_failed",
    }
    languages = {"uz_latn", "uz_cyrl", "ru"}
    for key in keys:
        assert set(GUEST_CLAIM_MESSAGES[key]) == languages
        assert all(GUEST_CLAIM_MESSAGES[key][lang].strip() for lang in languages)
