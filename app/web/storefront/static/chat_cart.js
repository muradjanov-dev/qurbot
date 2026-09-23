(async () => {
  'use strict';
  if (window.QB?.ready && !await window.QB.ready) return;
  const dialog = document.querySelector('[data-cart-dialog]');
  if (!dialog) return;
  const S = JSON.parse(document.getElementById('sales-strings').textContent);
  const form = dialog.querySelector('form');
  const lines = dialog.querySelector('[data-cart-lines]');
  const summary = dialog.querySelector('[data-checkout-summary]');
  const status = dialog.querySelector('[data-checkout-status]');
  const submit = dialog.querySelector('[data-checkout-submit]');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  let cart, quote = null, busy = false, key = crypto.randomUUID(), sentBody = null, requestMode = false;
  const hint = dialog.querySelector('[data-request-hint]');
  const node = (tag, text, cls) => {const n = document.createElement(tag); n.textContent = text; if (cls) n.className = cls; return n;};
  async function api(url, body, method = 'POST') {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
    const response = await fetch(url, {method: body === undefined ? 'GET' : method,
      credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: body === undefined ? undefined : JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      const fieldErrors = {address_text: S.address_invalid, contact_name: S.name_invalid,
        phone: S.phone_invalid, district_id: S.district_invalid};
      const field = Array.isArray(data.detail) ? data.detail.find(item => fieldErrors[item.loc?.at(-1)])?.loc.at(-1) : null;
      const message = (data.code === 'cart_conflict' || data.detail === 'cart_conflict') ? S.conflict
        : response.status === 401 || response.status === 403 ? S.session_error
        : field ? fieldErrors[field]
        : response.status === 422 && data.detail === 'invalid_contact' ? S.contact_invalid : data.error || S.error;
      const error = new Error(message);
      error.data = data; throw error;
    }
    return data;
    } finally {clearTimeout(timer);}
  }
  function invalidate() {quote = null; sentBody = null; key = crypto.randomUUID(); summary.replaceChildren(); submit.textContent = requestMode ? S.send_request : S.calculate;}
  function publish() {document.dispatchEvent(new CustomEvent('qurbot:cart-updated', {detail: cart}));}
  function lock(value) {
    busy = value;
    dialog.querySelectorAll('input, select, button').forEach(n => {n.disabled = value;});
    if (sentBody) dialog.querySelectorAll('input, select, [data-cart-lines] button').forEach(n => {n.disabled = true;});
    submit.disabled = value || (!cart?.lines.length && !sentBody);
  }
  function showQuote(value) {
    quote = value;
    summary.replaceChildren();
    value.items.forEach(item => summary.append(node('p', `${item.name} · ${item.qty} — ${item.cost}`)));
    summary.append(node('p', `${S.delivery}: ${value.delivery_total}`), node('strong', `${S.total}: ${value.grand_total}`));
    submit.textContent = S.confirm;
  }
  function draw() {
    if (!sentBody) requestMode = Boolean(cart.requires_confirmation || cart.lines.some(line => line.requires_confirmation));
    hint.hidden = !requestMode;
    lines.replaceChildren();
    if (!cart.lines.length) lines.append(node('p', S.empty_cart, 'empty'));
    for (const item of cart.lines) {
      const row = node('div', '', 'sales-cart-line');
      row.append(node('strong', item.canonical_name));
      if (item.requires_confirmation) row.append(node('small', S.price_request));
      const qty = document.createElement('input'); qty.type = 'text'; qty.inputMode = 'decimal'; qty.value = item.qty;
      qty.setAttribute('aria-label', item.canonical_name + ' ' + item.unit_code);
      const remove = node('button', S.remove, 'btn btn-ghost btn-sm'); remove.type = 'button';
      qty.disabled = remove.disabled = busy || Boolean(sentBody);
      row.append(qty, node('span', item.unit_code), remove); lines.append(row);
      if (item.line_total_uzs != null) {
        if (item.display_unit_price_uzs != null) {
          row.append(node('small', `${window.qurbotFormatUzs(item.display_unit_price_uzs)} ${S.currency} / ${item.unit_code}`));
        } else if (item.display_pack_price_uzs != null) {
          row.append(node('small', `${window.qurbotFormatUzs(item.display_pack_price_uzs)} ${S.currency} / ${item.display_pack_size} ${item.display_pack_unit}`));
        }
        row.append(node('strong', `${S.estimated_line_total}: ${window.qurbotFormatUzs(item.line_total_uzs)} ${S.currency}`));
      }
      async function change(amount) {
        if (busy) return;
        lock(true); status.textContent = '';
        try {
          cart = await api(`/api/cart/items/${item.canonical_id}`, {qty: amount, unit_code: item.unit_code, expected_revision: cart.revision}, 'PUT');
          await load(); invalidate(); publish();
        } catch (error) {status.textContent = error.message; await load();}
        finally {lock(false);}
      }
      qty.addEventListener('change', () => change(qty.value.trim().replace(',', '.')));
      remove.addEventListener('click', () => change('0'));
    }
    form.hidden = !cart.lines.length && !sentBody;
  }
  async function load() {cart = await api('/api/cart'); draw();}
  document.querySelector('[data-open-cart]').addEventListener('click', async () => {
    dialog.showModal(); status.textContent = ''; lock(true);
    form.querySelectorAll('.field').forEach(n => {n.hidden = false;}); submit.hidden = false;
    try {
      await load();
      if (form.elements.district.options.length === 1) {
        const options = await api('/api/checkout/options');
        options.districts.forEach(d => form.elements.district.add(new Option(d.name, d.id)));
        const contact = options.contact || {};
        for (const name of ['name', 'phone', 'address']) if (!form.elements[name].value && contact[name]) form.elements[name].value = contact[name];
        if (contact.district_id && !form.elements.district.value) form.elements.district.value = String(contact.district_id);
      }
      // Preserve the exact body/key after a timeout, so retries cannot duplicate orders.
      if (!sentBody) invalidate();
    } catch (error) {status.textContent = error.message;}
    finally {lock(false);}
  });
  dialog.querySelector('[data-close-cart]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-more-products]').addEventListener('click', () => {
    dialog.close(); location.assign('/catalog');
  });
  function validateContact() {
    const address = form.elements.address;
    address.setCustomValidity(address.value.trim().length < 5 ? S.address_invalid : '');
    const name = form.elements.name;
    name.setCustomValidity(!name.value.trim() ? S.name_invalid : '');
  }
  form.addEventListener('input', () => {validateContact(); if (!busy) invalidate();});
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || (!cart?.lines.length && !sentBody)) return;
    if (!sentBody) {
      validateContact();
      if (!form.reportValidity()) return;
    }
    const body = sentBody || {contact_name: form.elements.name.value.trim(), phone: form.elements.phone.value.trim(),
      district_id: Number(form.elements.district.value), address_text: form.elements.address.value.trim(),
      lat: form.elements.lat.value ? Number(form.elements.lat.value) : null,
      lng: form.elements.lng.value ? Number(form.elements.lng.value) : null,
      cart_revision: cart.revision, idempotency_key: key, strategy: quote?.strategy || null,
      expected_total: quote?.grand_total_raw || null};
    lock(true); status.textContent = '';
    try {
      if (requestMode) {
        sentBody = body;
        const data = await api('/api/sales-requests', body);
        status.replaceChildren(node('strong', S.request_sent.replace('{id}', data.request.id)));
        const link = node('a', S.requests); link.href = `/sales-requests#request-${data.request.id}`; status.append(link);
        sentBody = null; quote = null; key = crypto.randomUUID();
        cart = await api('/api/cart'); publish(); lines.replaceChildren(); summary.replaceChildren(); hint.hidden = true;
        form.querySelectorAll('.field').forEach(n => {n.hidden = true;}); submit.hidden = true;
        document.dispatchEvent(new CustomEvent('qurbot:handoff'));
      }
      else if (!quote) {const data = await api('/api/checkout/preview', body);
        if (data.requires_confirmation) {requestMode = true; hint.hidden = false; invalidate();}
        else showQuote(data.variant);}
      else {
        sentBody = body;
        const data = await api('/api/order', body);
        status.replaceChildren(node('strong', `${S.ordered} #${data.order_id}`));
        const link = node('a', S.orders); link.href = `/orders/${data.order_id}`; status.append(link);
        quote = null; sentBody = null; key = crypto.randomUUID();
        cart = await api('/api/cart'); publish(); lines.replaceChildren(); summary.replaceChildren();
        form.querySelectorAll('.field').forEach(n => {n.hidden = true;}); submit.hidden = true;
      }
    } catch (error) {
      status.textContent = error.message;
      if (error.data?.price_changed) {sentBody = null; key = crypto.randomUUID(); showQuote(error.data.variant);}
      else if (error.data?.requires_confirmation) {requestMode = true; hint.hidden = false; invalidate();}
      else if (error.data?.code === 'cart_conflict' || error.data?.detail === 'cart_conflict') {invalidate(); await load(); invalidate();}
      else if (error.data) {sentBody = null;}
    } finally {lock(false);}
  });
  if (new URLSearchParams(location.search).get('cart') === '1') document.querySelector('[data-open-cart]').click();
})();
