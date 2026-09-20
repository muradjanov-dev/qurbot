(async () => {
  'use strict';
  if (window.QB?.ready && !await window.QB.ready) return;
  const root = document.querySelector('[data-operator]');
  if (!root) return;
  const S = JSON.parse(document.getElementById('operator-strings').textContent);
  const adminId = Number(root.dataset.adminId);
  const list = root.querySelector('[data-inbox]'), log = root.querySelector('[data-thread-log]');
  const title = root.querySelector('[data-thread-title]'), mode = root.querySelector('[data-thread-mode]');
  const status = root.querySelector('[data-operator-status]'), form = root.querySelector('form');
  const claim = root.querySelector('[data-claim]'), finish = root.querySelector('[data-finish]');
  const more = root.querySelector('[data-more]');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const viewport = window.visualViewport;
  function fit() {
    if (viewport && viewport.scale !== 1) return;
    document.body.style.height = `${Math.min(viewport?.height || innerHeight,
      window.Telegram?.WebApp?.viewportHeight || innerHeight)}px`;
  }
  viewport?.addEventListener('resize', fit); window.addEventListener('resize', fit);
  window.Telegram?.WebApp?.onEvent?.('viewportChanged', fit); fit();
  let rows = [], filter = 'waiting', selected = null, cursor = 0, next = null;
  let pages = 1;
  let openRequests = false, requestSignature = '';
  const resolutionDrafts = new Map();
  let busy = false, polling = false, timer, stopped = false, owned = false;
  const drafts = new Map(), requests = new Map(), seen = new Set();
  const el = (tag, text, cls) => {const n = document.createElement(tag); n.textContent = text; if (cls) n.className = cls; return n;};
  async function api(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
    const response = await fetch('/api/chat/operator' + path, {method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: body === undefined ? undefined : JSON.stringify(body)});
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {stopped = true; owned = false; controls();}
      const error = new Error(S.error); error.status = response.status; throw error;
    }
    return await response.json();
    } finally {clearTimeout(timer);}
  }
  function controls() {
    form.elements.message.disabled = !owned || busy || stopped;
    form.querySelector('button').disabled = !owned || busy || stopped;
    claim.disabled = finish.disabled = busy || stopped;
    finish.disabled ||= openRequests;
    finish.title = openRequests ? S.resolve_first : '';
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
    if (!panel) {panel = el('section', '', 'sales-request-panel'); panel.dataset.salesRequests = ''; log.prepend(panel);}
    panel.replaceChildren();
    for (const item of items) {
      const card = el('article', '', 'card chat-product');
      card.append(el('h3', `${S.requests} #${item.id} · ${S['request_' + item.status]}`));
      card.append(el('p', `${item.contact_name} · ${item.phone}`), el('p', `${item.district_name || ''}, ${item.address}`));
      for (const line of item.items) card.append(el('p', `${line.name} — ${line.qty} ${line.unit_code} · ${line.requires_confirmation ? S.price_request : line.reference_unit_price == null ? '' : line.reference_unit_price + ' UZS'}`));
      if (item.resolution_note) card.append(el('p', item.resolution_note));
      if (owned && item.status === 'open') {
        const note = el('textarea'); note.placeholder = S.resolution_note; note.setAttribute('aria-label', S.resolution_note);
        note.maxLength = 2000; note.value = resolutionDrafts.get(item.id) || '';
        note.addEventListener('input', () => resolutionDrafts.set(item.id, note.value)); card.append(note);
        for (const outcome of ['agreed', 'cancelled']) {
          const button = el('button', S['request_' + outcome], 'btn btn-ghost'); button.type = 'button';
          button.addEventListener('click', async () => {
            if (busy || !note.value.trim()) {note.focus(); return;}
            busy = true; controls(); button.disabled = true;
            try {
              await api(`/sales-requests/${item.id}/resolve`, {outcome, note: note.value.trim()});
              resolutionDrafts.delete(item.id); requestSignature = ''; await refreshThread();
            } catch (_) {status.textContent = S.error;}
            finally {busy = false; button.disabled = false; controls();}
          }); card.append(button);
        }
      }
      panel.append(card);
    }
  }
  function renderList() {
    const scrollTop = list.scrollTop;
    list.replaceChildren();
    const visible = rows.filter(row => filter === 'waiting' ? row.status === 'waiting' : filter === 'mine' ? row.mine : row.status === 'human' && !row.mine);
    if (!visible.length) list.append(el('p', S.empty, 'empty'));
    for (const row of visible) {
      const button = el('button', '', 'operator-row' + (row.id === selected ? ' selected' : ''));
      button.type = 'button'; button.setAttribute('aria-pressed', String(row.id === selected));
      button.append(el('strong', row.name || `${S.customer} ${row.user_id}`), el('span', row.preview),
        el('small', new Date(row.updated_at).toLocaleString(document.documentElement.lang)));
      if (row.unread) button.append(el('b', row.unread, 'operator-unread'));
      button.addEventListener('click', () => choose(row.id)); list.append(button);
    }
    more.hidden = !next;
    list.scrollTop = scrollTop;
  }
  async function refreshList(append = false) {
    const scope = filter;
    if (append) pages++;
    let loaded = [], after = 0;
    for (let page = 0; page < pages; page++) {
      const data = await api(`?scope=${scope}&after_id=${after}`);
      if (scope !== filter) return;
      loaded.push(...data.conversations); after = data.next_cursor;
      if (!after) break;
    }
    rows = loaded; next = after; renderList();
  }
  function clearThread() {
    openRequests = false; requestSignature = '';
    selected = null; cursor = 0; owned = false; seen.clear(); log.replaceChildren();
    title.textContent = S.select; mode.textContent = ''; claim.hidden = finish.hidden = true;
    root.classList.remove('thread-open'); controls();
  }
  async function choose(id) {
    if (busy) return;
    openRequests = false; requestSignature = '';
    if (selected) drafts.set(selected, form.elements.message.value);
    selected = id; cursor = 0; owned = false; seen.clear(); log.replaceChildren();
    form.elements.message.value = drafts.get(id) || ''; root.classList.add('thread-open');
    claim.hidden = finish.hidden = true; controls(); renderList();
    await refreshThread();
  }
  async function refreshThread() {
    if (!selected) return;
    const id = selected;
    try {
      const data = await api(`/${id}?after=${cursor}`);
      if (selected !== id) return;
      const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100;
      for (const message of data.messages) {
        if (seen.has(message.id)) continue;
        seen.add(message.id);
        const item = el('article', '', 'chat-message' + (message.role === 'operator' ? ' chat-message-you' : ''));
        item.append(el('small', S[message.role] || 'QurBot', 'chat-message-author'), el('div', message.text, 'chat-message-text'));
        log.append(item); cursor = Math.max(cursor, message.sequence);
      }
      const row = rows.find(r => r.id === id);
      title.textContent = row?.name || `${S.customer} #${id}`;
      owned = data.status === 'human' && data.operator_id === adminId;
      mode.textContent = data.status === 'waiting' ? S.waiting : owned ? S.mine : S.others;
      claim.hidden = data.status !== 'waiting'; finish.hidden = !owned;
      await refreshRequests(id);
      if (selected !== id) return;
      controls(); if (nearBottom) log.scrollTop = log.scrollHeight;
      if (!document.hidden && cursor) await api(`/${id}/read`, {sequence: cursor});
    } catch (error) {
      if (selected !== id) return;
      if (error.status === 404) clearThread(); else status.textContent = S.error;
    }
  }
  async function action(name) {
    if (!selected || busy) return;
    if (name === 'close' && !confirm(S.finish_confirm)) return;
    busy = true; controls(); status.textContent = '';
    try {
      await api(`/${selected}/${name}`, {});
      if (name === 'close') clearThread();
      else {
        filter = 'mine'; pages = 1;
        root.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === filter)));
      }
      await refreshList(); await refreshThread();
    }
    catch (_) {status.textContent = S.error; await refreshThread();}
    finally {busy = false; controls();}
  }
  claim.addEventListener('click', () => action('claim')); finish.addEventListener('click', () => action('close'));
  root.querySelector('[data-back]').addEventListener('click', () => root.classList.remove('thread-open'));
  root.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    filter = button.dataset.filter; pages = 1;
    list.scrollTop = 0;
    root.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    refreshList().catch(() => {status.textContent = S.error;});
  }));
  more.addEventListener('click', async () => {try {await refreshList(true);} catch (_) {status.textContent = S.error;}});
  form.addEventListener('submit', async event => {
    event.preventDefault(); const text = form.elements.message.value.trim();
    if (!selected || !owned || busy || !text) return;
    const id = selected;
    let request = requests.get(id);
    if (!request || request.text !== text) {request = {text, request_id: crypto.randomUUID()}; requests.set(id, request);}
    busy = true; controls(); status.textContent = '';
    try {
      await api(`/${id}/messages`, request); requests.delete(id); drafts.delete(id);
      if (selected === id) form.elements.message.value = '';
      await refreshThread();
    } catch (_) {status.textContent = S.error;}
    finally {busy = false; controls();}
  });
  async function poll() {
    if (polling || stopped || document.hidden) return;
    polling = true;
    try {await refreshList(); await refreshThread();} catch (_) {status.textContent = S.error;}
    finally {polling = false; if (!stopped) timer = setTimeout(poll, 3000);}
  }
  document.addEventListener('visibilitychange', () => {clearTimeout(timer); if (!document.hidden) poll();});
  window.addEventListener('pagehide', () => clearTimeout(timer));
  window.addEventListener('pageshow', () => {clearTimeout(timer); poll();});
  await poll();
  const initial = Number(new URLSearchParams(location.search).get('conversation'));
  if (Number.isSafeInteger(initial) && initial > 0) await choose(initial);
})();
