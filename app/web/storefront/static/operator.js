/* Admin inbox. API responses are data; customer-provided text stays in text nodes. */
(async () => {
  'use strict';
  if (window.QB?.ready && !await window.QB.ready) return;
  const root = document.querySelector('[data-operator]');
  if (!root) return;

  const S = JSON.parse(document.getElementById('operator-strings').textContent);
  const adminId = Number(root.dataset.adminId);
  const list = root.querySelector('[data-inbox]');
  const inboxStatus = root.querySelector('[data-inbox-status]');
  const search = root.querySelector('[data-search]');
  const clearSearch = root.querySelector('[data-search-clear]');
  const retryList = root.querySelector('[data-retry-list]');
  const thread = root.querySelector('.operator-thread');
  const log = root.querySelector('[data-thread-log]');
  const threadEmpty = root.querySelector('[data-thread-empty]');
  const threadStatus = root.querySelector('[data-thread-status]');
  const retryThread = root.querySelector('[data-retry-thread]');
  const jumpLatest = root.querySelector('[data-jump-latest]');
  const title = root.querySelector('[data-thread-title]');
  const mode = root.querySelector('[data-thread-mode]');
  const form = root.querySelector('[data-operator-form]');
  const input = form.elements.message;
  const send = form.querySelector('button[type="submit"]');
  const claim = root.querySelector('[data-claim]');
  const finish = root.querySelector('[data-finish]');
  const more = root.querySelector('[data-more]');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const main = document.querySelector('#main');
  const viewport = window.visualViewport;
  const telegram = window.Telegram?.WebApp;
  const MOBILE_QUERY = '(max-width: 760px)';
  const TRANSCRIPT_PAGE_SIZE = 100;

  let rows = [];
  let filter = 'waiting';
  let query = '';
  let queryTimer;
  let queryPending = false;
  let listPages = 1;
  let next = null;
  let listVersion = 0;
  let listRequest = 0;
  let listBusy = false;
  let selected = null;
  let selectedVersion = 0;
  let cursor = 0;
  let latestPageConfirmed = false;
  let newWhileAway = 0;
  let openRequests = false;
  let requestSignature = '';
  let owned = false;
  let ownershipRefreshing = false;
  let busy = false;
  let stopped = false;
  let polling = false;
  let timer;
  let threadRequest = 0;
  const drafts = new Map();
  const messageRequests = new Map();
  const resolutionDrafts = new Map();
  const seen = new Set();
  const readSequences = new Map();

  const el = (tag, text = '', className = '') => {
    const node = document.createElement(tag);
    if (text !== null && text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  };

  function fitWorkspace() {
    if (viewport && viewport.scale !== 1) return;
    if (!main) return;
    const rect = main.getBoundingClientRect();
    const visualTop = viewport?.offsetTop || 0;
    const visualHeight = Math.min(
      viewport?.height || window.innerHeight,
      telegram?.viewportHeight || window.innerHeight,
    );
    const top = Math.max(rect.top, visualTop);
    const bottom = Math.min(rect.bottom, visualTop + visualHeight);
    root.style.setProperty('--operator-visible-height', `${Math.max(0, bottom - top)}px`);
  }

  function setInboxStatus(message = '', failed = false) {
    inboxStatus.textContent = message;
    inboxStatus.dataset.error = String(failed);
    retryList.hidden = !failed;
  }

  function setThreadStatus(message = '', failed = false) {
    threadStatus.textContent = message;
    threadStatus.dataset.error = String(failed);
    retryThread.hidden = !failed;
  }

  function controls() {
    const hasSelection = selected !== null;
    form.hidden = !hasSelection || !owned;
    input.disabled = !hasSelection || !owned || busy || stopped;
    send.disabled = !hasSelection || !owned || busy || stopped;
    claim.disabled = busy || stopped;
    finish.disabled = busy || stopped || openRequests;
    finish.title = openRequests ? S.resolve_first : '';
    more.disabled = listBusy;
  }

  async function api(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`/api/chat/operator${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          stopped = true;
          owned = false;
          controls();
        }
        const error = new Error(S.error);
        error.status = response.status;
        throw error;
      }
      return response.status === 204 ? {} : await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  function formatTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    const lang = document.body.dataset.lang;
    const locale = lang === 'ru' ? 'ru-RU' : lang === 'uz_cyrl' ? 'uz-Cyrl-UZ' : 'uz-Latn-UZ';
    try {
      return new Intl.DateTimeFormat(locale, {dateStyle: 'short', timeStyle: 'short'}).format(date);
    } catch (_) {
      return date.toLocaleString();
    }
  }

  function renderList() {
    const scrollTop = list.scrollTop;
    const focusedId = document.activeElement?.closest?.('[data-conversation-id]')?.dataset.conversationId;
    const fragment = document.createDocumentFragment();
    if (!rows.length) {
      const message = queryPending ? S.searching : query ? S.no_results : S.empty;
      fragment.append(el('p', message, 'empty'));
    }
    for (const row of rows) {
      const id = Number(row.id);
      const button = el('button', '', `operator-row${id === selected ? ' selected' : ''}`);
      button.type = 'button';
      button.dataset.conversationId = String(id);
      button.setAttribute('aria-pressed', String(id === selected));
      if (id === selected) button.setAttribute('aria-current', 'true');
      button.append(el('strong', row.name || `${S.customer} #${row.user_id}`));
      button.append(el('span', row.preview || ''));
      const time = el('time', formatTime(row.updated_at));
      if (row.updated_at) time.dateTime = row.updated_at;
      button.append(time);
      const unread = Number(row.unread || 0);
      if (unread > 0) {
        const badge = el('b', unread > 99 ? '99+' : unread, 'operator-unread');
        badge.setAttribute('aria-label', `${unread} ${S.unread}`);
        button.append(badge);
      }
      button.addEventListener('click', () => choose(id));
      fragment.append(button);
    }
    list.replaceChildren(fragment);
    list.scrollTop = scrollTop;
    more.hidden = !next;
    if (focusedId) {
      list.querySelector(`[data-conversation-id="${CSS.escape(focusedId)}"]`)?.focus({preventScroll: true});
    }
  }

  function queueParams(scope, afterId) {
    const params = new URLSearchParams({scope, after_id: String(afterId)});
    if (query) params.set('q', query);
    return `?${params.toString()}`;
  }

  async function refreshList() {
    if (queryPending) return;
    const version = listVersion;
    const requestId = ++listRequest;
    const scope = filter;
    const searchQuery = query;
    const pages = listPages;
    let loaded = [];
    let afterId = 0;
    listBusy = true;
    if (!rows.length) setInboxStatus(S.inbox_loading);
    controls();
    try {
      for (let page = 0; page < pages; page++) {
        const data = await api(queueParams(scope, afterId));
        if (version !== listVersion || requestId !== listRequest || scope !== filter || searchQuery !== query) return;
        loaded.push(...(data.conversations || []));
        afterId = data.next_cursor || 0;
        if (!afterId) break;
      }
      if (version !== listVersion || requestId !== listRequest) return;
      rows = loaded;
      next = afterId || null;
      renderList();
      setInboxStatus('');
    } catch (_) {
      if (version === listVersion && requestId === listRequest) {
        setInboxStatus(S.inbox_error, true);
      }
      throw _;
    } finally {
      if (requestId === listRequest) {
        listBusy = false;
        controls();
      }
    }
  }

  function isAtLatest() {
    return log.scrollHeight - log.scrollTop - log.clientHeight <= 64;
  }

  function threadIsVisible() {
    if (window.matchMedia(MOBILE_QUERY).matches && !root.classList.contains('thread-open')) return false;
    if (log.hidden || window.getComputedStyle(thread).display === 'none') return false;
    const rect = log.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  async function markReadIfAllowed(id = selected) {
    if (
      id === null || id !== selected || !cursor || !latestPageConfirmed || busy ||
      ownershipRefreshing || stopped || document.hidden || !threadIsVisible() || !isAtLatest()
    ) return;
    const previous = readSequences.get(id) || 0;
    if (cursor <= previous) return;
    const sequence = cursor;
    readSequences.set(id, sequence);
    try {
      await api(`/${id}/read`, {sequence});
    } catch (_) {
      if (readSequences.get(id) === sequence) readSequences.set(id, previous);
    }
  }

  function updateJump(showNew = false, count = 0) {
    if (showNew) newWhileAway += count;
    const show = selected !== null && newWhileAway > 0 && !isAtLatest();
    jumpLatest.hidden = !show;
    if (show) jumpLatest.textContent = `${S.jump_new} (${newWhileAway})`;
  }

  function appendMessages(messages) {
    const atLatest = isAtLatest();
    let added = 0;
    log.querySelector('[data-no-messages]')?.remove();
    for (const message of messages || []) {
      const key = message.id ?? message.sequence;
      if (key === undefined || seen.has(String(key))) continue;
      seen.add(String(key));
      const sequence = Number(message.sequence || 0);
      cursor = Math.max(cursor, sequence);
      const item = el('article', '', `chat-message${message.role === 'operator' ? ' chat-message-you' : ''}`);
      item.dataset.messageSequence = String(sequence);
      const role = message.role === 'operator' ? 'operator' : message.role === 'assistant' ? 'assistant' : message.role === 'system' ? 'system' : 'user';
      item.append(el('small', S[role] || S.system, 'chat-message-author'));
      item.append(el('div', message.text ?? message.content ?? '', 'chat-message-text'));
      log.append(item);
      added++;
    }
    if (added && atLatest) {
      log.scrollTop = log.scrollHeight;
      newWhileAway = 0;
    }
    updateJump(added > 0 && !atLatest, added);
    return added;
  }

  async function refreshRequests(id) {
    const data = await api(`/${id}/sales-requests`);
    if (selected !== id) return;
    const items = data.requests || [];
    openRequests = items.some(item => item.status === 'open');
    const signature = JSON.stringify([items, owned]);
    if (signature === requestSignature) return;
    requestSignature = signature;
    let panel = log.querySelector('[data-sales-requests]');
    if (!panel) {
      panel = el('section', '', 'sales-request-panel operator-sales-requests');
      panel.dataset.salesRequests = '';
      log.prepend(panel);
    }
    panel.replaceChildren();
    for (const item of items) {
      const card = el('article', '', 'card chat-product');
      card.append(el('h3', `${S.requests} #${item.id} · ${S[`request_${item.status}`] || item.status}`));
      card.append(el('p', `${item.contact_name} · ${item.phone}`));
      card.append(el('p', `${item.district_name || ''}, ${item.address}`));
      if (item.lat != null && item.lng != null) {
        const pin = el('a', `${item.lat}, ${item.lng}`, 'btn btn-ghost btn-sm');
        pin.href = `https://www.openstreetmap.org/?mlat=${encodeURIComponent(item.lat)}&mlon=${encodeURIComponent(item.lng)}#map=16/${encodeURIComponent(item.lat)}/${encodeURIComponent(item.lng)}`;
        pin.target = '_blank';
        pin.rel = 'noopener';
        card.append(pin);
      }
      for (const line of item.items || []) {
        const price = line.requires_confirmation
          ? S.price_request
          : line.reference_unit_price == null
            ? ''
            : `${window.qurbotFormatUzs(line.reference_unit_price)} ${S.currency}`;
        card.append(el('p', `${line.name} — ${line.qty} ${line.unit_code}${price ? ` · ${price}` : ''}`));
      }
      if (item.resolution_note) card.append(el('p', item.resolution_note));
      if (owned && item.status === 'open') {
        const note = el('textarea');
        note.placeholder = S.resolution_note;
        note.setAttribute('aria-label', S.resolution_note);
        note.maxLength = 2000;
        note.value = resolutionDrafts.get(item.id) || '';
        note.addEventListener('input', () => resolutionDrafts.set(item.id, note.value));
        card.append(note);
        for (const outcome of ['agreed', 'cancelled']) {
          const button = el('button', S[`request_${outcome}`], 'btn btn-ghost');
          button.type = 'button';
          button.addEventListener('click', async () => {
            if (busy || !note.value.trim()) { note.focus(); return; }
            busy = true;
            controls();
            try {
              await api(`/sales-requests/${item.id}/resolve`, {outcome, note: note.value.trim()});
              resolutionDrafts.delete(item.id);
              requestSignature = '';
              await refreshThread();
            } catch (_) {
              setThreadStatus(S.thread_error, true);
            } finally {
              busy = false;
              controls();
              markReadIfAllowed();
            }
          });
          card.append(button);
        }
      }
      panel.append(card);
    }
  }

  function renderThreadMeta(data, id) {
    const row = rows.find(item => Number(item.id) === id);
    title.textContent = row?.name || `${S.customer} #${row?.user_id || id}`;
    owned = data.status === 'human' && Number(data.operator_id) === adminId;
    if (data.status === 'waiting') mode.textContent = S.claim_hint;
    else mode.textContent = owned ? S.mine : S.others;
    claim.hidden = data.status !== 'waiting';
    finish.hidden = !owned;
    controls();
  }

  async function refreshThread() {
    if (selected === null) return;
    const id = selected;
    const version = selectedVersion;
    const requestId = ++threadRequest;
    const after = cursor;
    ownershipRefreshing = true;
    retryThread.hidden = true;
    if (!log.querySelector('.chat-message')) setThreadStatus(S.thread_loading);
    try {
      const data = await api(`/${id}?after=${after}`);
      if (id !== selected || version !== selectedVersion || requestId !== threadRequest) return;
      const messages = data.messages || [];
      latestPageConfirmed = messages.length < TRANSCRIPT_PAGE_SIZE;
      appendMessages(messages);
      cursor = Math.max(cursor, Number(data.next_sequence || 0));
      if (!log.querySelector('.chat-message') && cursor === 0) {
        log.append(el('p', S.no_messages, 'operator-no-messages'));
        log.lastElementChild.dataset.noMessages = '';
      }
      renderThreadMeta(data, id);
      await refreshRequests(id);
      if (id !== selected || version !== selectedVersion || requestId !== threadRequest) return;
      setThreadStatus('');
      fitWorkspace();
      ownershipRefreshing = false;
      controls();
      await markReadIfAllowed(id);
    } catch (error) {
      if (id !== selected || version !== selectedVersion || requestId !== threadRequest) return;
      if (error.status === 404) {
        clearThread();
      } else {
        setThreadStatus(S.thread_error, true);
        retryThread.hidden = false;
      }
    } finally {
      if (id === selected && version === selectedVersion && requestId === threadRequest) {
        ownershipRefreshing = false;
        controls();
      }
    }
  }

  function saveDraft() {
    if (selected !== null) drafts.set(selected, input.value);
  }

  function clearThread() {
    saveDraft();
    selectedVersion++;
    threadRequest++;
    selected = null;
    cursor = 0;
    latestPageConfirmed = false;
    newWhileAway = 0;
    ownershipRefreshing = false;
    openRequests = false;
    requestSignature = '';
    owned = false;
    seen.clear();
    log.replaceChildren();
    log.hidden = true;
    threadEmpty.hidden = false;
    title.textContent = S.select;
    mode.textContent = '';
    claim.hidden = finish.hidden = true;
    jumpLatest.hidden = true;
    retryThread.hidden = true;
    setThreadStatus('');
    root.classList.remove('thread-open');
    document.body.classList.remove('operator-thread-open');
    controls();
    renderList();
  }

  async function choose(id) {
    if (busy || !Number.isSafeInteger(id) || id <= 0) return;
    saveDraft();
    selectedVersion++;
    threadRequest++;
    selected = id;
    cursor = 0;
    latestPageConfirmed = false;
    newWhileAway = 0;
    openRequests = false;
    requestSignature = '';
    owned = false;
    seen.clear();
    log.replaceChildren();
    log.hidden = false;
    threadEmpty.hidden = true;
    input.value = drafts.get(id) || '';
    root.classList.add('thread-open');
    document.body.classList.add('operator-thread-open');
    claim.hidden = finish.hidden = true;
    jumpLatest.hidden = true;
    setThreadStatus(S.thread_loading);
    controls();
    renderList();
    fitWorkspace();
    await refreshThread();
  }

  async function action(name) {
    if (selected === null || busy) return;
    if (name === 'close' && !window.confirm(S.finish_confirm)) return;
    const id = selected;
    busy = true;
    controls();
    setThreadStatus('');
    try {
      await api(`/${id}/${name}`, {});
      if (name === 'close') {
        clearThread();
        listVersion++;
        listPages = 1;
        await refreshList();
        return;
      }
      filter = 'mine';
      listPages = 1;
      next = null;
      listVersion++;
      root.querySelectorAll('[data-filter]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.filter === filter));
      });
      await refreshList();
      await refreshThread();
    } catch (_) {
      setThreadStatus(S.error, true);
      await refreshThread();
    } finally {
      busy = false;
      controls();
      markReadIfAllowed();
    }
  }

  function beginSearch() {
    clearTimeout(queryTimer);
    queryPending = true;
    listVersion++;
    listRequest++;
    rows = [];
    listPages = 1;
    next = null;
    setInboxStatus(S.searching);
    renderList();
    clearSearch.hidden = !search.value;
    queryTimer = setTimeout(() => {
      query = search.value.trim().slice(0, 100);
      queryPending = false;
      refreshList().catch(() => {});
    }, 300);
  }

  function setFilter(value) {
    if (!['waiting', 'mine', 'others'].includes(value)) return;
    clearTimeout(queryTimer);
    queryPending = false;
    query = search.value.trim().slice(0, 100);
    filter = value;
    listVersion++;
    listPages = 1;
    next = null;
    list.scrollTop = 0;
    root.querySelectorAll('[data-filter]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.filter === filter));
    });
    refreshList().catch(() => {});
  }

  async function loadMore() {
    if (!next || listBusy || queryPending) return;
    const previousPages = listPages;
    listPages++;
    try {
      await refreshList();
    } catch (_) {
      listPages = previousPages;
    }
  }

  function scrollChanged() {
    if (isAtLatest()) {
      newWhileAway = 0;
      jumpLatest.hidden = true;
      markReadIfAllowed();
    } else if (newWhileAway > 0) {
      updateJump();
    }
  }

  async function poll() {
    if (polling || stopped || document.hidden) return;
    polling = true;
    try {
      if (!queryPending) await refreshList();
      if (selected !== null) await refreshThread();
    } catch (_) {
      // Each visible region already has its own retry message.
    } finally {
      polling = false;
      if (!stopped && !document.hidden) timer = setTimeout(poll, 3000);
    }
  }

  search.addEventListener('input', beginSearch);
  clearSearch.addEventListener('click', () => {
    search.value = '';
    search.focus();
    beginSearch();
  });
  retryList.addEventListener('click', () => refreshList().catch(() => {}));
  retryThread.addEventListener('click', () => refreshThread().catch(() => {}));
  more.addEventListener('click', loadMore);
  root.querySelectorAll('[data-filter]').forEach(button => {
    button.addEventListener('click', () => setFilter(button.dataset.filter));
  });
  root.querySelector('[data-back]').addEventListener('click', () => {
    saveDraft();
    root.classList.remove('thread-open');
    document.body.classList.remove('operator-thread-open');
  });
  claim.addEventListener('click', () => action('claim'));
  finish.addEventListener('click', () => action('close'));
  log.addEventListener('scroll', scrollChanged, {passive: true});
  jumpLatest.addEventListener('click', () => {
    log.scrollTop = log.scrollHeight;
    newWhileAway = 0;
    jumpLatest.hidden = true;
    markReadIfAllowed();
  });
  input.addEventListener('input', saveDraft);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const text = input.value.trim();
    if (selected === null || !owned || busy || !text) return;
    const id = selected;
    let request = messageRequests.get(id);
    if (!request || request.text !== text) {
      request = {text, request_id: window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`};
      messageRequests.set(id, request);
    }
    busy = true;
    controls();
    setThreadStatus('');
    try {
      await api(`/${id}/messages`, request);
      messageRequests.delete(id);
      drafts.delete(id);
      if (selected === id) input.value = '';
      await refreshThread();
    } catch (_) {
      setThreadStatus(S.thread_error, true);
    } finally {
      busy = false;
      controls();
      markReadIfAllowed(id);
    }
  });

  viewport?.addEventListener('resize', fitWorkspace);
  viewport?.addEventListener('scroll', fitWorkspace);
  window.addEventListener('resize', fitWorkspace);
  telegram?.onEvent?.('viewportChanged', fitWorkspace);
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (!document.hidden) poll();
  });
  window.addEventListener('pagehide', () => clearTimeout(timer));
  window.addEventListener('pageshow', () => {
    clearTimeout(timer);
    if (!document.hidden) poll();
  });

  fitWorkspace();
  try {
    await refreshList();
  } catch (_) {
    // The inbox owns the loading and retry state.
  }
  const initial = Number(new URLSearchParams(location.search).get('conversation'));
  if (Number.isSafeInteger(initial) && initial > 0) await choose(initial);
  if (!stopped && !document.hidden) timer = setTimeout(poll, 3000);
})();
