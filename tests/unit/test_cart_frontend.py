"""Execute the browser store against a fake HTTP server, without a browser dependency."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_durable_browser_cart_retries_and_decimal_quantities() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute storefront JavaScript")
    root = Path(__file__).resolve().parents[2]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const local = new Map();
const drafts = new Map();
const storage = map => ({getItem: key => map.get(key) || null,
  setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key)});
let revision = 4;
let lines = [{canonical_id: 1, qty: '2', unit_code: 'dona', status: 'ok'}];
let conflict = false;
const requests = [];
const sandbox = {
  window: {QB: {authed: true, i18n: {}}, localStorage: storage(local)},
  document: {querySelector: selector => selector === 'meta[name="csrf-token"]'
    ? {content: 'csrf-test'} : null, querySelectorAll: () => [], addEventListener: () => {}},
  localStorage: storage(local), sessionStorage: storage(drafts),
  crypto: {randomUUID: () => 'stable-merge-id'},
  fetch: async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : undefined;
    requests.push({url, method: options.method, headers: options.headers, body});
    let ok = true;
    if (options.method === 'PUT') {
      assert.equal(options.headers['X-CSRF-Token'], 'csrf-test');
      assert.equal(body.expected_revision, revision);
      if (conflict) { ok = false; lines[0].qty = '9'; }
      else lines[0].qty = body.qty;
      revision++;
    }
    if (options.method === 'POST') {
      assert.equal(body.merge_key, 'stable-merge-id');
      assert.equal(body.expected_revision, revision);
      assert.equal(body.lines[0].qty, '5');
    }
    return {ok, json: async () => ({ok, revision, lines: JSON.parse(JSON.stringify(lines))})};
  }
};
const source = fs.readFileSync('app/web/storefront/static/app.js', 'utf8')
  .replace(/\}\)\(\);\s*$/,
    'window.cartTest = {loadCart, basket, quantityUnits, quantityText};})();');
vm.runInNewContext(source, sandbox);
(async () => {
  const store = sandbox.window.cartTest;
  assert.equal(store.quantityText(store.quantityUnits('999999.000001')), '999999.000001');
  assert.equal(store.quantityText(store.quantityUnits('0.1') + store.quantityUnits('0.2')), '0.3');
  assert.equal(store.quantityUnits('NaN'), null);
  assert.equal(await store.loadCart(), true);
  const edit = store.basket.load();
  edit[0].qty = '3';
  assert.equal(await store.basket.save(edit), true);
  assert.equal(store.basket.load()[0].qty, '3');
  assert.equal(local.has('qb_basket_v1'), false);
  conflict = true;
  const stale = store.basket.load();
  stale[0].qty = '8';
  assert.equal(await store.basket.save(stale), false);
  assert.equal(store.basket.load()[0].qty, '9');
  assert.deepEqual(requests.slice(-2).map(r => r.method), ['PUT', 'GET']);
  local.set('qb_basket_v1', JSON.stringify([
    {canonical_id: 1, qty: '5', unit_code: 'dona', status: 'ok'}]));
  assert.equal(await store.loadCart(), true);
  assert.equal(local.has('qb_basket_v1'), false);
  assert.equal(local.has('qb_cart_merge_key'), false);
  assert.equal(store.basket.load()[0].qty, '9');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", script], cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
