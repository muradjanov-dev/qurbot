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
  set innerHTML(value) { this._text = String(value); this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute(name, value) { this[name] = value; }
  querySelector(selector) { return this.selectors?.[selector] || null; }
  querySelectorAll(selector) {
    const matches = selector === 'input[data-drop-local-index]:checked' &&
      this.dataset.dropLocalIndex !== undefined && this.checked ? [this] : [];
    return matches.concat(this.children.flatMap(child => child.querySelectorAll(selector)));
  }
}

const source = fs.readFileSync('app/web/storefront/static/app.js', 'utf8');

function response(ok, body) {
  return {ok, json: async () => JSON.parse(JSON.stringify(body))};
}

function makeBrowser({localLines, serverLines, revision, fetchRequest, mergeKey, failSetKeys = []}) {
  const local = new Map([['qb_basket_v1', JSON.stringify(localLines)]]);
  if (mergeKey) local.set('qb_cart_merge_key', mergeKey);
  const session = new Map();
  const storageControl = {failSetKeys: new Set(failSetKeys)};
  const storage = map => ({getItem: key => map.has(key) ? map.get(key) : null,
    setItem: (key, value) => {
      if (storageControl.failSetKeys.has(key)) throw new Error('QuotaExceededError');
      map.set(key, String(value));
    },
    removeItem: key => map.delete(key)});
  const card = new Element('div');
  card.hidden = true;
  card.dataset = {
    dropLabel: 'Remove from saved items',
    reviewFailed: 'Saved items are still here. Try again.',
    reviewConflict: 'These items use different units.',
    reviewChanged: 'Saved items changed. Review the updated list.',
    reviewRetrying: 'Updating the cart…',
    reviewDiscarded: 'Selected items were removed.',
    reviewStorageFailed: 'Could not remove the selected items.'
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
  const basket = new Element('div');
  const actions = new Element('div');
  const quote = new Element('section');
  const documentHandlers = {};
  const state = {serverLines, revision};
  const requests = [];
  let uuidCounter = 0;
  const sandbox = {
    window: {QB: {authed: true, lang: 'uz_latn', i18n: {}}, localStorage: storage(local)},
    document: {
      hidden: false,
      querySelector: selector => selector === 'meta[name="csrf-token"]' ? {content: 'csrf-test'}
        : selector === '[data-local-cart-review]' ? card
        : selector === '[data-basket]' ? basket
        : selector === '[data-basket-actions]' ? actions
        : selector === '[data-quote]' ? quote : null,
      querySelectorAll: () => [],
      addEventListener: (name, handler) => { documentHandlers[name] = handler; },
      createElement: tag => new Element(tag),
      createTextNode: text => { const node = new Element('#text'); node.textContent = text; return node; }
    },
    localStorage: storage(local),
    sessionStorage: storage(session),
    crypto: {randomUUID: () => 'merge-id-' + (++uuidCounter)},
    setTimeout,
    clearTimeout,
    fetch: async (url, options = {}) => {
      const body = options.body ? JSON.parse(options.body) : undefined;
      requests.push({url, method: options.method, body});
      if (url === '/api/cart') return response(true, {ok: true, revision: state.revision, lines: state.serverLines});
      if (url === '/api/cart/merge') return fetchRequest(body, state, requests.length);
      throw new Error('Unexpected request: ' + url + ' ' + options.method);
    }
  };
  vm.runInNewContext(source, sandbox);
  return {
    local,
    storageControl,
    state,
    requests,
    card,
    draftList,
    message,
    retry,
    drop,
    basket,
    actions,
    ready: () => documentHandlers.DOMContentLoaded()
  };
}

async function selectedDraftCanBeDroppedBeforeRetrying() {
  let mergeAttempts = 0;
  const browser = makeBrowser({
    localLines: [
      {canonical_id: 1, qty: '5', unit_code: 'dona', status: 'ok', canonical_name: 'Tile'},
      {canonical_id: 2, qty: '7', unit_code: 'qop', status: 'ok', canonical_name: 'Cement'},
      {canonical_id: 3, qty: '4', unit_code: 'qop', status: 'ok', canonical_name: 'Sand'}
    ],
    serverLines: [
      {canonical_id: 1, qty: '2', unit_code: 'qop', status: 'ok', canonical_name: 'Tile'},
      {canonical_id: 2, qty: '6', unit_code: 'qop', status: 'ok', canonical_name: 'Cement'}
    ],
    revision: 7,
    fetchRequest: async (body, state) => {
      mergeAttempts += 1;
      assert.equal(body.merge_key, 'merge-id-1');
      if (mergeAttempts === 1) {
        return response(false, {ok: false, code: 'unit_conflict', revision: state.revision, lines: state.serverLines});
      }
      assert.equal(body.expected_revision, 8);
      assert.deepEqual(body.lines.map(line => line.canonical_id), [2, 3]);
      if (mergeAttempts === 2) return response(false, {ok: false, error: 'Temporarily unavailable'});
      const byId = new Map(state.serverLines.map(line => [line.canonical_id, {...line}]));
      body.lines.forEach(line => {
        const old = byId.get(line.canonical_id);
        if (!old) byId.set(line.canonical_id, {
          ...line, status: 'ok', canonical_name: line.canonical_id === 3 ? 'Sand' : 'Cement'
        });
        else old.qty = String(Math.max(Number(old.qty), Number(line.qty)));
      });
      state.serverLines = [...byId.values()];
      state.revision += 1;
      return response(true, {ok: true, revision: state.revision, lines: state.serverLines});
    }
  });

  await browser.ready();
  assert.equal(browser.card.hidden, false);
  assert.match(browser.draftList.textContent, /5 dona/);
  assert.equal(browser.local.has('qb_basket_v1'), true);

  const conflictingCheckbox = browser.draftList.children[0].children[0].children[0];
  conflictingCheckbox.checked = true;
  conflictingCheckbox.handlers.change();
  assert.equal(browser.drop.disabled, false);
  browser.drop.handlers.click();
  assert.deepEqual(JSON.parse(browser.local.get('qb_basket_v1')).map(line => line.canonical_id), [2, 3]);
  assert.equal(mergeAttempts, 1, 'discarding selected local items must not trigger a merge');

  // Another tab changed the durable cart after the original conflict.
  browser.state.revision = 8;
  browser.state.serverLines[1].qty = '8';
  await browser.retry.handlers.click();
  assert.equal(browser.card.hidden, false);
  assert.equal(browser.message.textContent, 'Saved items are still here. Try again.');
  assert.equal(browser.local.has('qb_basket_v1'), true);

  await browser.retry.handlers.click();
  assert.equal(browser.card.hidden, true);
  assert.equal(browser.local.has('qb_basket_v1'), false);
  assert.equal(browser.local.has('qb_cart_merge_key'), false);
  assert.equal(mergeAttempts, 3);
  const posts = browser.requests.filter(request => request.url === '/api/cart/merge');
  assert.deepEqual(posts.map(request => request.body.expected_revision), [7, 8, 8]);
  posts.forEach(request => assert.equal(request.body.merge_key, 'merge-id-1'));
  posts.forEach(request => {
    const index = browser.requests.indexOf(request);
    assert.equal(browser.requests[index - 1].url, '/api/cart', 'each attempt refreshes the server revision first');
  });
  assert.equal(browser.state.serverLines.find(line => line.canonical_id === 2).qty, '8', 'merge keeps the server maximum');
  assert.equal(browser.state.serverLines.find(line => line.canonical_id === 3).qty, '4');
  assert.match(browser.basket.textContent, /Sand/);
}

async function completedOrderIsNotResurrectedAfterLostMergeResponse() {
  const receiptKeys = new Set();
  let mergeAttempts = 0;
  const browser = makeBrowser({
    localLines: [
      {canonical_id: 9, qty: '5', unit_code: 'dona', status: 'ok', canonical_name: 'Stone'},
      {canonical_id: 10, qty: '3', unit_code: 'qop', status: 'ok', canonical_name: 'Sand'}
    ],
    serverLines: [],
    revision: 0,
    fetchRequest: async (body, state) => {
      mergeAttempts += 1;
      if (receiptKeys.has(body.merge_key)) {
        return response(true, {ok: true, revision: state.revision, lines: state.serverLines});
      }
      receiptKeys.add(body.merge_key);
      body.lines.forEach(line => {
        state.serverLines.push({
          ...line, status: 'ok', canonical_name: line.canonical_id === 9 ? 'Stone' : 'Sand'
        });
      });
      if (mergeAttempts === 1) {
        state.revision += 1;
        throw new Error('The successful merge response was lost');
      }
      state.revision += 1;
      return response(true, {ok: true, revision: state.revision, lines: state.serverLines});
    }
  });

  await browser.ready();
  assert.equal(browser.card.hidden, false);
  assert.equal(browser.local.has('qb_basket_v1'), true);
  const mergeKey = browser.local.get('qb_cart_merge_key');

  // The customer placed the order before reopening the browser; replaying its
  // merge receipt returns the now-empty account cart. A selected local discard
  // must keep the same receipt key for the remaining lines from this batch.
  browser.state.serverLines = [];
  browser.state.revision += 1;
  const selectedCheckbox = browser.draftList.children[0].children[0].children[0];
  selectedCheckbox.checked = true;
  selectedCheckbox.handlers.change();
  browser.drop.handlers.click();
  assert.deepEqual(JSON.parse(browser.local.get('qb_basket_v1')).map(line => line.canonical_id), [10]);
  assert.equal(browser.local.get('qb_cart_merge_key'), mergeKey);
  browser.storageControl.failSetKeys.add('qb_cart_merge_key');

  await browser.retry.handlers.click();
  assert.equal(mergeAttempts, 2);
  assert.equal(browser.requests.filter(request => request.url === '/api/cart/merge')[1].body.merge_key, mergeKey);
  assert.deepEqual(browser.state.serverLines, []);
  assert.equal(browser.actions.hidden, true);
  assert.equal(browser.card.hidden, true);
  assert.equal(browser.local.has('qb_basket_v1'), false);
}

async function newMergeKeyMustBeStoredBeforeLoadOrRetry() {
  let mergeAttempts = 0;
  let browser;
  browser = makeBrowser({
    localLines: [{canonical_id: 20, qty: '2', unit_code: 'dona', status: 'ok', canonical_name: 'Brick'}],
    serverLines: [],
    revision: 0,
    failSetKeys: ['qb_cart_merge_key'],
    fetchRequest: async (body, state) => {
      mergeAttempts += 1;
      assert.equal(body.merge_key, browser.local.get('qb_cart_merge_key'));
      state.serverLines = body.lines.map(line => ({...line, status: 'ok', canonical_name: 'Brick'}));
      state.revision += 1;
      return response(true, {ok: true, revision: state.revision, lines: state.serverLines});
    }
  });

  await browser.ready();
  assert.equal(mergeAttempts, 0, 'load must not submit an ephemeral key');
  assert.equal(browser.card.hidden, false);
  assert.equal(browser.local.has('qb_basket_v1'), true);
  assert.equal(browser.local.has('qb_cart_merge_key'), false);

  await browser.retry.handlers.click();
  assert.equal(mergeAttempts, 0, 'manual retry must also wait for a durable key');
  assert.equal(browser.card.hidden, false);
  assert.equal(browser.local.has('qb_basket_v1'), true);

  browser.storageControl.failSetKeys.delete('qb_cart_merge_key');
  await browser.retry.handlers.click();
  assert.equal(mergeAttempts, 1);
  assert.equal(browser.card.hidden, true);
  assert.equal(browser.local.has('qb_basket_v1'), false);
}

async function storedKeyIsUsedWhenStorageWritesFailDuringLoad() {
  const expectedKey = 'saved-receipt-key';
  const browser = makeBrowser({
    localLines: [{canonical_id: 30, qty: '3', unit_code: 'qop', status: 'ok', canonical_name: 'Cement'}],
    serverLines: [],
    revision: 5,
    mergeKey: expectedKey,
    failSetKeys: ['qb_cart_merge_key'],
    fetchRequest: async (body, state) => {
      assert.equal(body.merge_key, expectedKey);
      // This saved receipt represents a merge that already completed and whose
      // cart was later emptied by an order.
      return response(true, {ok: true, revision: state.revision, lines: []});
    }
  });

  await browser.ready();
  assert.deepEqual(browser.state.serverLines, []);
  assert.equal(browser.card.hidden, true);
  assert.equal(browser.local.has('qb_basket_v1'), false);
  assert.equal(browser.requests.filter(request => request.url === '/api/cart/merge')[0].body.merge_key, expectedKey);
  assert.equal(browser.local.has('qb_cart_merge_key'), false, 'success clears the acknowledged source key');
}

async function failedSelectedDeletionKeepsTheSavedDraft() {
  const original = [
    {canonical_id: 40, qty: '5', unit_code: 'dona', status: 'ok', canonical_name: 'Tile'},
    {canonical_id: 41, qty: '2', unit_code: 'qop', status: 'ok', canonical_name: 'Sand'}
  ];
  const browser = makeBrowser({
    localLines: original,
    serverLines: [{canonical_id: 40, qty: '1', unit_code: 'qop', status: 'ok', canonical_name: 'Tile'}],
    revision: 2,
    fetchRequest: async (_body, state) => response(false, {
      ok: false, code: 'unit_conflict', revision: state.revision, lines: state.serverLines
    })
  });
  await browser.ready();
  const originalStorageValue = browser.local.get('qb_basket_v1');
  browser.storageControl.failSetKeys.add('qb_basket_v1');
  const checkbox = browser.draftList.children[0].children[0].children[0];
  checkbox.checked = true;
  checkbox.handlers.change();
  browser.drop.handlers.click();

  assert.equal(browser.local.get('qb_basket_v1'), originalStorageValue);
  assert.equal(browser.card.hidden, false);
  assert.match(browser.message.textContent, /Could not remove/);
  assert.match(browser.draftList.textContent, /5 dona/);
}

(async () => {
  await newMergeKeyMustBeStoredBeforeLoadOrRetry();
  await storedKeyIsUsedWhenStorageWritesFailDuringLoad();
  await failedSelectedDeletionKeepsTheSavedDraft();
  await completedOrderIsNotResurrectedAfterLostMergeResponse();
  await selectedDraftCanBeDroppedBeforeRetrying();
})().catch(error => { console.error(error); process.exitCode = 1; });
