/* Shared bot/web conversation. All server text is rendered as text nodes. */
(async () => {
  'use strict';
  if (window.QB?.ready && !await window.QB.ready) return;
  const root = document.querySelector('[data-chat]');
  const form = root?.querySelector('[data-chat-form]');
  if (!form) return;
  const strings = JSON.parse(document.getElementById('chat-strings').textContent);
  const log = root.querySelector('[data-chat-log]');
  const empty = root.querySelector('[data-chat-empty]');
  const status = root.querySelector('[data-chat-status]');
  const modeLabel = root.querySelector('[data-chat-mode]');
  const operator = root.querySelector('[data-chat-operator]');
  const input = form.elements.message;
  const send = root.querySelector('[data-chat-send]');
  const requestsRoot = root.querySelector('[data-chat-requests]');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const POLL_MS = 2500;
  const MAX_BACKOFF_MS = 30000;
  const HTTP_TIMEOUT_MS = 20000;
  const seen = new Set();
  const requests = new Map();
  let cursor = 0;
  let timer;
  let polling = false;
  let stopped = false;
  let ready = false;
  let submitting = false;
  let operatorBusy = false;
  let storageKey;
  let mode = '';
  let backoff = POLL_MS;

  // Keep the composer above both the keyboard and Telegram's changing viewport.
  const viewport = window.visualViewport;
  const telegram = window.Telegram?.WebApp;
  function fitViewport() {
    if (viewport && viewport.scale !== 1) return;
    const height = Math.min(viewport?.height || window.innerHeight,
      telegram?.viewportHeight || window.innerHeight);
    document.body.style.setProperty('--chat-viewport-height', `${height}px`);
    document.body.style.setProperty('--chat-viewport-top', `${viewport?.offsetTop || 0}px`);
  }
  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = `${input.scrollHeight + 2}px`;
  }
  let followingLatest = true;
  log.addEventListener('scroll', () => {
    followingLatest = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  });
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if (followingLatest) log.scrollTop = log.scrollHeight;
    }).observe(log);
  }
  input.addEventListener('input', resizeInput);
  window.addEventListener('resize', fitViewport);
  viewport?.addEventListener('resize', fitViewport);
  viewport?.addEventListener('scroll', fitViewport);
  telegram?.onEvent?.('viewportChanged', fitViewport);
  fitViewport();
  resizeInput();

  function saveRequests() {
    if (!storageKey) return;
    try {
      const pending = [...requests.values()].filter(item => !item.node.hidden).map(item => ({
        request_id: item.request_id, text: item.text, job_id: item.job_id,
        status: item.status === 'sending' ? 'unknown' : item.status,
      }));
      sessionStorage.setItem(storageKey, JSON.stringify(pending.slice(-100)));
    } catch (_) { /* Chat still works when browser storage is unavailable. */ }
  }

  function restoreRequests(conversationId) {
    if (storageKey || !conversationId) return;
    storageKey = `qurbot:chat:${conversationId}`;
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
      if (Array.isArray(saved)) {
        saved.slice(-100).forEach(item => {
          if (typeof item.request_id === 'string' && typeof item.text === 'string') updateRequest(item);
        });
      }
    } catch (_) { /* Ignore corrupt or unavailable local state. */ }
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);
    try {
      const response = await fetch(path, {
        ...options,
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      });
      if (!response.ok) {
        const error = new Error(String(response.status));
        error.status = response.status;
        if (response.status === 401 || response.status === 403) {
          stopped = true;
          ready = false;
          status.textContent = strings.session;
          controls();
        }
        throw error;
      }
      return response.status === 204 ? {} : await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  function controls() {
    input.disabled = !ready || stopped;
    send.disabled = !ready || stopped || submitting;
    operator.disabled = !ready || stopped || operatorBusy || mode !== 'ai';
  }

  function setMode(value) {
    mode = value;
    modeLabel.textContent = strings[value === 'human' ? 'assigned' : value === 'waiting' ? 'requested' : 'ai'];
    controls();
  }

  function publishCart(cart) {
    document.querySelectorAll('[data-basket-count]').forEach(badge => {
      badge.textContent = String(cart.lines.length);
      badge.hidden = !cart.lines.length;
    });
    document.dispatchEvent(new CustomEvent('qurbot:cart-updated', { detail: cart }));
  }

  function productCard(product) {
    const id = String(product.product_id ?? product.canonical_id ?? product.id ?? '');
    const unitCode = product.unit_code || product.price_unit_code || product.unit;
    if (!/^\d+$/.test(id)) return null;
    const card = element('article', 'chat-product card');
    const title = element('a', 'chat-product-title', product.name || product.name_uz || product.name_ru || id);
    title.href = `/product/${encodeURIComponent(id)}`;
    card.append(title);
    const photo = element('img', 'chat-product-image');
    photo.src = `/media/product/${encodeURIComponent(id)}`; photo.alt = ''; photo.loading = 'lazy';
    photo.addEventListener('error', () => {photo.hidden = true;}); card.prepend(photo);
    if (product.price_from_uzs == null || product.price_on_request || product.stock_unverified || !/^[a-z][a-z0-9]*$/.test(unitCode || '')) {
      card.append(element('p', 'notice warn tiny', strings.confirmation));
    }
    if (product.price_from_uzs !== undefined && product.price_from_uzs !== null) {
      card.append(element('p', 'chat-product-price', `${new Intl.NumberFormat(document.documentElement.lang).format(Number(product.price_from_uzs))} UZS${product.unit ? ` / ${product.unit}` : ''}`));
    }
    const row = element('form', 'chat-product-actions');
    const label = element('label', 'field', `${strings.qty} (${unitCode})`);
    const qty = element('input');
    qty.type = 'text';
    qty.inputMode = 'decimal';
    qty.pattern = '[0-9]+([.,][0-9]+)?';
    qty.required = true;
    qty.maxLength = 20;
    qty.value = '1';
    label.append(qty);
    const add = element('button', 'btn btn-primary btn-sm', strings.add);
    add.type = 'submit';
    const feedback = element('p', 'tiny');
    feedback.setAttribute('role', 'status');
    row.append(label, add);
    card.append(row, feedback);
    row.addEventListener('submit', async event => {
      event.preventDefault();
      const amount = qty.value.trim().replace(',', '.');
      if (!/^\d+(?:\.\d+)?$/.test(amount) || !/[1-9]/.test(amount)) {
        feedback.textContent = strings.cart_error;
        qty.focus();
        return;
      }
      add.disabled = true;
      feedback.textContent = '';
      try {
        const cart = await api('/api/cart');
        const existing = (cart.lines || []).find(item => String(item.canonical_id) === id);
        if (existing && existing.unit_code !== unitCode) {
          feedback.textContent = strings.unit_conflict;
          return;
        }
        const result = await api(`/api/cart/items/${encodeURIComponent(id)}`, {
          method: 'PUT',
          body: JSON.stringify({ expected_revision: cart.revision, qty: amount, unit_code: unitCode }),
        });
        feedback.replaceChildren(element('strong', '', `${product.name || id} — ${amount} ${unitCode}. ${strings.added}`));
        const open = element('button', 'btn btn-primary btn-sm', strings.view_cart); open.type = 'button';
        open.onclick = () => document.querySelector('[data-open-cart]').click();
        const more = element('button', 'btn btn-ghost btn-sm', strings.more_products); more.type = 'button';
        more.onclick = () => document.querySelector('#chat-message').focus();
        const edit = element('button', 'btn btn-ghost btn-sm', strings.edit_qty); edit.type = 'button'; edit.onclick = () => qty.focus();
        feedback.append(open, more, edit);
        publishCart(result);
      } catch (error) {
        feedback.textContent = stopped ? strings.session : error.status === 409 ? strings.cart_conflict : strings.cart_error;
      } finally {
        add.disabled = stopped;
      }
    });
    return card;
  }

  function addMessages(messages) {
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
    let added = false;
    for (const message of messages || []) {
      if (message.id === undefined || seen.has(String(message.id))) continue;
      seen.add(String(message.id));
      const role = ['user', 'customer'].includes(message.role) ? 'you' : message.role === 'operator' ? 'operator_name' : message.role === 'assistant' ? 'assistant' : 'system';
      const article = element('article', `chat-message chat-message-${role}`);
      article.append(element('p', 'chat-message-author', strings[role]));
      article.append(element('p', 'chat-message-text', message.text ?? message.content ?? ''));
      for (const product of message.cards || []) {
        const card = productCard(product);
        if (card) article.append(card);
      }
      log.append(article);
      const numericId = Number(message.sequence);
      if (Number.isSafeInteger(numericId)) cursor = Math.max(cursor, numericId);
      added = true;
    }
    empty.hidden = seen.size > 0;
    if (added && atBottom) log.scrollTop = log.scrollHeight;
  }

  function updateRequest(record) {
    const id = record.request_id;
    if (!id) return;
    let item = requests.get(id);
    if (!item) {
      const node = element('div', 'chat-request');
      const label = element('p', 'tiny');
      label.setAttribute('role', 'status');
      const retry = element('button', 'btn btn-ghost btn-sm', strings.retry);
      retry.type = 'button';
      retry.hidden = true;
      retry.addEventListener('click', () => submitRequest(item));
      node.append(label, retry);
      const handoff = element('button', 'btn btn-ghost btn-sm', operator.textContent);
      handoff.type = 'button'; handoff.hidden = true;
      handoff.addEventListener('click', () => operator.click()); node.append(handoff);
      requestsRoot.append(node);
      item = { request_id: id, node, label, retry, handoff };
      requests.set(id, item);
    }
    Object.assign(item, record);
    const done = ['completed', 'human', 'cancelled'].includes(item.status);
    const failed = ['failed', 'error', 'unknown'].includes(item.status);
    item.node.hidden = done;
    item.handoff.hidden = true;
    item.label.textContent = `${strings.request} ${id} · ${strings[failed ? 'failed' : item.status === 'sending' ? 'sending' : 'pending']}`;
    if (!done && !failed && ['pending', 'running'].includes(item.status)) {
      const age = Math.max(0, (Date.now() - new Date(item.created_at || Date.now()).getTime()) / 1000);
      const copy = age >= 60 ? strings.progress_slow : strings[`progress_${((item.job_id || 0) + Math.floor(age / 10)) % 7}`];
      item.handoff.hidden = age < 60 || mode !== 'ai';
      item.label.textContent = `${strings[item.status === 'running' ? 'progress_running' : 'progress_queued']} · ${copy}`;
    }
    item.retry.hidden = !failed;
    item.retry.disabled = stopped || item.busy || false;
    saveRequests();
    return item;
  }

  function receive(data) {
    addMessages(data.messages);
    // Job status "human" means handed off, not necessarily assigned to an operator.
    if (Array.isArray(data.messages) && ['ai', 'waiting', 'human'].includes(data.status)) setMode(data.status);
    for (const request of data.requests || []) updateRequest(request);
    if (data.request) updateRequest(data.request);
    if (data.request_id) updateRequest(data);
  }

  async function submitRequest(item) {
    if (item.busy || stopped) return;
    item.busy = true;
    submitting = true;
    updateRequest({ request_id: item.request_id, status: 'sending' });
    controls();
    try {
      const data = await api('/api/chat/messages', {
        method: 'POST',
        body: JSON.stringify({ request_id: item.request_id, text: item.text }),
      });
      updateRequest({ request_id: item.request_id, status: 'pending' });
      receive(data);
      saveRequests();
      if (input.value.trim() === item.text) {
        input.value = '';
        resizeInput();
      }
      followingLatest = true;
      log.scrollTop = log.scrollHeight;
      status.textContent = '';
    } catch (error) {
      updateRequest({ request_id: item.request_id, status: 'unknown' });
      if (!stopped) status.textContent = error.status === 429 ? strings.limit : error.status ? strings.failed : strings.connection;
    } finally {
      item.busy = false;
      submitting = false;
      updateRequest({ request_id: item.request_id });
      controls();
      schedule(0);
    }
  }

  function schedule(delay = backoff) {
    clearTimeout(timer);
    if (!stopped && !document.hidden) timer = setTimeout(poll, delay);
  }

  async function poll() {
    if (polling || stopped || document.hidden) return;
    polling = true;
    try {
      const data = await api(`/api/chat?after=${encodeURIComponent(cursor)}`);
      receive(data);
      restoreRequests(data.conversation_id);
      // A bot/AI turn can change the shared cart without a card click in this tab.
      // Leave the initial load/guest merge to app.js before publishing later updates.
      if (ready && data.messages?.length) publishCart(await api('/api/cart'));
      const active = [...requests.values()].filter(item => item.job_id && !item.node.hidden);
      const jobs = await Promise.allSettled(active.map(item => api(`/api/chat/jobs/${encodeURIComponent(item.job_id)}`)));
      let jobError = false;
      for (const result of jobs) {
        if (result.status === 'fulfilled') updateRequest(result.value);
        else jobError = true;
      }
      ready = true;
      controls();
      if (!stopped) status.textContent = jobError ? strings.connection : '';
      backoff = POLL_MS;
    } catch (_) {
      if (!stopped) status.textContent = strings.connection;
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    } finally {
      polling = false;
      schedule();
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!input.value.trim() || submitting || !ready || stopped) return;
    // Preserve the original ID on an ambiguous send instead of duplicating it.
    const unresolved = [...requests.values()].find(item => item.text === input.value.trim() && item.status === 'unknown');
    const item = unresolved || updateRequest({ request_id: crypto.randomUUID(), text: input.value.trim(), status: 'sending' });
    submitRequest(item);
  });

  operator.addEventListener('click', async () => {
    if (!window.confirm(strings.handoff_confirm)) return;
    const menu = operator.closest('details');
    if (menu) menu.open = false;
    operatorBusy = true;
    controls();
    try {
      receive(await api('/api/chat/handoff', { method: 'POST', body: '{}' }));
    } catch (_) {
      if (!stopped) status.textContent = strings.failed;
    } finally {
      operatorBusy = false;
      controls();
      schedule(0);
    }
  });
  document.addEventListener('visibilitychange', () => document.hidden ? clearTimeout(timer) : schedule(0));
  window.addEventListener('online', () => schedule(0));
  document.addEventListener('qurbot:handoff', () => schedule(0));
  window.addEventListener('pagehide', () => clearTimeout(timer));
  window.addEventListener('pageshow', () => schedule(0));
  poll();
})();
