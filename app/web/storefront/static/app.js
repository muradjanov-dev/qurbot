/* QurBot storefront.
 *
 * The basket lives in this file, in localStorage: it is the customer's own
 * scratch list and should survive a reload without an account. Nothing here
 * decides a price -- every total on screen came back from the server, which
 * recomputes it from live offers and ignores anything this file claims.
 */
(function () {
  "use strict";

  var QB = window.QB || { lang: "uz_latn", authed: false, i18n: {} };
  var T = QB.i18n || {};
  var STORE_KEY = "qb_basket_v1";
  var STRATEGY_KEY = "qb_strategy";

  /* ── helpers ─────────────────────────────────────────────────────── */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  var toastTimer = null;
  function toast(message) {
    var box = $("[data-toast]");
    if (!box || !message) return;
    box.textContent = message;
    box.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.hidden = true; }, 3200);
  }

  function fill(template, values) {
    return String(template || "").replace(/\{(\w+)\}/g, function (whole, key) {
      return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : whole;
    });
  }

  async function postJSON(url, body) {
    var response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    if (response.status === 401) return { ok: false, error: T.loginRequired, unauthorized: true };
    if (!response.ok) return { ok: false, error: T.error };
    try {
      return await response.json();
    } catch (err) {
      return { ok: false, error: T.error };
    }
  }

  /* ── basket store ────────────────────────────────────────────────── */

  var basket = {
    load: function () {
      try {
        var raw = window.localStorage.getItem(STORE_KEY);
        var parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        return [];
      }
    },
    save: function (lines) {
      try {
        window.localStorage.setItem(STORE_KEY, JSON.stringify(lines));
      } catch (err) { /* private mode: the basket is then per-page, still usable */ }
      syncCount();
    },
    clear: function () { basket.save([]); },
    nextNo: function (lines) {
      return lines.reduce(function (max, line) { return Math.max(max, line.line_no || 0); }, 0);
    },
    orderable: function (lines) {
      return lines.filter(function (line) { return line.status === "ok" && line.canonical_id; });
    },
    payload: function (lines) {
      return basket.orderable(lines).map(function (line) {
        return {
          line_no: line.line_no,
          canonical_id: line.canonical_id,
          qty: String(line.qty),
          unit_code: line.unit_code || null
        };
      });
    }
  };

  function syncCount() {
    var total = basket.load().length;
    $$("[data-basket-count]").forEach(function (node) {
      node.textContent = String(total);
      node.hidden = total === 0;
    });
  }

  /* ── home: send the list ─────────────────────────────────────────── */

  function initListForm() {
    var form = $("[data-list-form]");
    if (!form) return;

    $$("[data-example]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var input = $("[data-list-input]", form);
        input.value = chip.dataset.example;
        input.focus();
      });
    });

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var input = $("[data-list-input]", form);
      var button = $("[data-submit]", form);
      var text = (input.value || "").trim();
      if (!text) return;

      button.disabled = true;
      var original = button.textContent;
      button.textContent = T.loading;

      var lines = basket.load();
      var result = await postJSON("/api/basket/parse", { text: text, start_no: basket.nextNo(lines) });

      button.disabled = false;
      button.textContent = original;

      if (!result.ok) { toast(result.error || T.parseFailed); return; }
      basket.save(lines.concat(result.lines));
      window.location.href = "/basket";
    });
  }

  /* ── product page: add to basket ─────────────────────────────────── */

  function initQtyWidgets() {
    $$("[data-qty]").forEach(function (widget) {
      var input = $("input", widget);
      $$("button", widget).forEach(function (button) {
        button.addEventListener("click", function () {
          var step = Number(button.dataset.step || 1);
          var next = (parseFloat(input.value) || 0) + step;
          input.value = String(Math.max(Number(input.min || 1), Math.round(next * 1000) / 1000));
        });
      });
    });
  }

  function initAddToBasket() {
    var button = $("[data-add-product]");
    if (!button) return;

    button.addEventListener("click", async function () {
      var qtyInput = $("[data-qty] input");
      var lines = basket.load();
      button.disabled = true;
      var result = await postJSON("/api/basket/product", {
        canonical_id: Number(button.dataset.addProduct),
        qty: qtyInput ? qtyInput.value : "1",
        line_no: basket.nextNo(lines) + 1
      });
      button.disabled = false;

      if (!result.ok) { toast(result.error || T.error); return; }
      lines.push(result.line);
      basket.save(lines);
      toast(T.added);
    });
  }

  /* ── basket page ─────────────────────────────────────────────────── */

  function renderBasket() {
    var host = $("[data-basket]");
    if (!host) return;

    var lines = basket.load();
    host.innerHTML = "";

    if (!lines.length) {
      var empty = el("div", "empty");
      empty.appendChild(el("p", null, T.basketEmpty));
      empty.appendChild(el("p", "tiny", T.basketEmptyHint));
      host.appendChild(empty);
      $("[data-basket-actions]").hidden = true;
      $("[data-quote]").innerHTML = "";
      return;
    }
    $("[data-basket-actions]").hidden = false;

    lines.forEach(function (line, index) {
      host.appendChild(renderLine(line, index, lines));
    });
  }

  function renderLine(line, index, lines) {
    var wrap = el("div", "line" + (line.status === "choose" ? " is-choose" : line.status === "unknown" ? " is-unknown" : ""));

    var head = el("div", "line-head");
    var left = el("div", "grow");

    var title = el("div", "line-name", line.status === "ok" ? (line.canonical_name || line.parsed_name) : (line.parsed_name || line.raw_text));
    left.appendChild(title);

    if (line.status === "choose") {
      left.appendChild(el("span", "badge warn", T.chooseKind));
    } else if (line.status === "unknown") {
      left.appendChild(el("span", "badge bad", T.notFound));
    }
    head.appendChild(left);

    var remove = el("button", "btn btn-sm btn-danger", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", T.remove);
    remove.addEventListener("click", function () {
      lines.splice(index, 1);
      basket.save(lines);
      renderBasket();
    });
    head.appendChild(remove);
    wrap.appendChild(head);

    var actions = el("div", "line-actions");
    var qty = el("div", "qty");
    var minus = el("button", null, "−");
    minus.type = "button";
    var input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.value = String(line.qty);
    input.setAttribute("aria-label", T.qty);
    var plus = el("button", null, "+");
    plus.type = "button";

    function commit(value) {
      var parsed = parseFloat(String(value).replace(",", "."));
      if (!isFinite(parsed) || parsed <= 0) { input.value = String(line.qty); return; }
      line.qty = String(Math.round(parsed * 1000) / 1000);
      input.value = line.qty;
      basket.save(lines);
    }
    minus.addEventListener("click", function () { commit((parseFloat(line.qty) || 1) - 1); });
    plus.addEventListener("click", function () { commit((parseFloat(line.qty) || 0) + 1); });
    input.addEventListener("change", function () { commit(input.value); });

    qty.appendChild(minus);
    qty.appendChild(input);
    qty.appendChild(plus);
    actions.appendChild(qty);
    actions.appendChild(el("span", "muted tiny", line.unit_code || ""));
    wrap.appendChild(actions);

    if (line.status === "choose" && line.candidates && line.candidates.length) {
      var options = el("div", "chips");
      line.candidates.forEach(function (candidate) {
        var chip = el("button", "chip", candidate.price ? candidate.name + " · " + candidate.price : candidate.name);
        chip.type = "button";
        chip.addEventListener("click", function () {
          line.status = "ok";
          line.canonical_id = candidate.canonical_id;
          line.canonical_name = candidate.name;
          line.candidates = [];
          basket.save(lines);
          renderBasket();
        });
        options.appendChild(chip);
      });
      wrap.appendChild(options);
    }

    return wrap;
  }

  function initBasketPage() {
    var host = $("[data-basket]");
    if (!host) return;

    renderBasket();

    var addForm = $("[data-add-form]");
    if (addForm) {
      var toggle = $("[data-add-toggle]");
      toggle.addEventListener("click", function () {
        addForm.hidden = !addForm.hidden;
        if (!addForm.hidden) $("textarea", addForm).focus();
      });
      addForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        var field = $("textarea", addForm);
        var text = (field.value || "").trim();
        if (!text) return;

        var lines = basket.load();
        var result = await postJSON("/api/basket/parse", { text: text, start_no: basket.nextNo(lines) });
        if (!result.ok) { toast(result.error || T.parseFailed); return; }
        basket.save(lines.concat(result.lines));
        field.value = "";
        addForm.hidden = true;
        renderBasket();
      });
    }

    var clear = $("[data-clear]");
    if (clear) {
      clear.addEventListener("click", function () {
        basket.clear();
        renderBasket();
        $("[data-quote]").innerHTML = "";
      });
    }

    var calc = $("[data-calculate]");
    if (calc) calc.addEventListener("click", function () { runQuote(calc); });
  }

  async function runQuote(button) {
    var lines = basket.load();
    var payload = basket.payload(lines);
    var host = $("[data-quote]");
    if (!payload.length) { toast(T.nothingConfirmed); return; }

    button.disabled = true;
    var original = button.textContent;
    button.textContent = T.loading;

    var result = await postJSON("/api/quote", { lines: payload });

    button.disabled = false;
    button.textContent = original;

    if (!result.ok) { toast(result.error || T.quoteEmpty); return; }
    renderQuote(host, result.variants, payload);
    host.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderQuote(host, variants, payload) {
    host.innerHTML = "";
    if (!variants.length) {
      host.appendChild(el("div", "empty", T.quoteEmpty));
      return;
    }

    var state = { index: 0 };
    var tabs = el("div", "variant-tabs");
    var card = el("div", "card");

    variants.forEach(function (variant, index) {
      var tab = el("button", "variant-tab" + (index === 0 ? " is-active" : ""), variant.title);
      tab.type = "button";
      tab.addEventListener("click", function () {
        state.index = index;
        $$(".variant-tab", tabs).forEach(function (node, position) {
          node.classList.toggle("is-active", position === index);
        });
        drawVariant(card, variants[index], payload);
      });
      tabs.appendChild(tab);
    });

    if (variants.length > 1) host.appendChild(tabs);
    host.appendChild(card);
    drawVariant(card, variants[0], payload);
  }

  function drawVariant(card, variant, payload) {
    card.innerHTML = "";
    card.appendChild(el("h2", null, variant.title));

    var list = el("div", "quote-lines");
    variant.items.forEach(function (item) {
      var row = el("div", "quote-line");
      var left = el("div", "q-name");
      left.appendChild(el("div", null, item.name));
      left.appendChild(el("div", "q-qty", item.qty));
      row.appendChild(left);
      row.appendChild(el("div", "price", item.cost));
      list.appendChild(row);
    });
    card.appendChild(list);

    card.appendChild(totalRow(T.itemsTotal, variant.items_total));
    card.appendChild(totalRow(T.delivery, variant.delivery_total));
    card.appendChild(totalRow(T.grandTotal, variant.grand_total, true));
    if (variant.delivery_note) card.appendChild(el("p", "muted tiny", variant.delivery_note));

    if (variant.savings) card.appendChild(el("p", "notice ok", variant.savings));
    var meta = el("p", "muted tiny");
    meta.textContent = variant.coverage + " · " + variant.eta;
    card.appendChild(meta);

    if (variant.missing && variant.missing.length) {
      card.appendChild(el("p", "notice warn", T.notFound + ": " + variant.missing.join(", ")));
    }

    var actions = el("div", "row");
    actions.style.marginTop = "16px";

    var select = el("a", "btn btn-primary", T.select);
    select.href = "/checkout?strategy=" + encodeURIComponent(variant.strategy);
    select.addEventListener("click", function () {
      try { window.localStorage.setItem(STRATEGY_KEY, variant.strategy); } catch (err) { /* ignore */ }
    });
    actions.appendChild(select);

    var pdf = el("button", "btn", T.pdf);
    pdf.type = "button";
    pdf.addEventListener("click", function () { downloadPdf(pdf, payload, variant.strategy); });
    actions.appendChild(pdf);

    card.appendChild(actions);
  }

  function totalRow(label, value, grand) {
    var row = el("div", "total-row" + (grand ? " grand" : ""));
    row.appendChild(el("span", null, label));
    row.appendChild(el("span", "price", value));
    return row;
  }

  async function downloadPdf(button, payload, strategy) {
    button.disabled = true;
    try {
      var response = await fetch("/api/quote/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lines: payload, strategy: strategy })
      });
      if (!response.ok) { toast(T.error); return; }
      var blob = await response.blob();
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "qurbot-taklif.pdf";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    } catch (err) {
      toast(T.error);
    } finally {
      button.disabled = false;
    }
  }

  /* ── checkout ────────────────────────────────────────────────────── */

  function initCheckout() {
    var root = $("[data-checkout]");
    if (!root) return;

    var strategy = root.dataset.strategy || readStrategy();
    var summary = $("[data-order-summary]");
    var confirm = $("[data-confirm]");
    var expectedTotal = null;
    var payload = basket.payload(basket.load());

    if (!payload.length) {
      summary.innerHTML = "";
      summary.appendChild(el("div", "empty", T.basketEmpty));
      confirm.disabled = true;
      return;
    }

    (async function () {
      summary.innerHTML = "";
      summary.appendChild(el("p", "muted", T.loading));
      var result = await postJSON("/api/quote", { lines: payload, strategy: strategy });
      if (!result.ok) {
        summary.innerHTML = "";
        summary.appendChild(el("div", "empty", result.error || T.quoteEmpty));
        confirm.disabled = true;
        return;
      }
      var variant = pickVariant(result.variants, strategy);
      expectedTotal = variant.grand_total_raw;
      summary.innerHTML = "";
      drawSummary(summary, variant);
    })();

    initGeolocation();

    confirm.addEventListener("click", async function () {
      var phone = $("[data-phone]").value.trim();
      if (!phone) { toast(T.phoneRequired); return; }

      var chosen = $$("[name='address_choice']").filter(function (node) { return node.checked; })[0];
      var body = {
        lines: payload,
        strategy: strategy,
        phone: phone,
        comment: $("[data-comment]").value.trim(),
        expected_total: expectedTotal
      };

      if (chosen && chosen.value !== "new") {
        body.address_id = Number(chosen.value);
      } else {
        var text = $("[data-address-text]").value.trim();
        if (!text) { toast(T.addressRequired); return; }
        body.address_text = text;
        var lat = $("[data-lat]").value;
        var lng = $("[data-lng]").value;
        if (lat && lng) { body.lat = Number(lat); body.lng = Number(lng); }
      }

      confirm.disabled = true;
      var original = confirm.textContent;
      confirm.textContent = T.loading;
      var result = await postJSON("/api/order", body);
      confirm.disabled = false;
      confirm.textContent = original;

      if (result.ok) {
        basket.clear();
        window.location.href = result.redirect || "/orders";
        return;
      }
      if (result.price_changed && result.variant) {
        expectedTotal = result.variant.grand_total_raw;
        summary.innerHTML = "";
        drawSummary(summary, result.variant);
      }
      if (result.unauthorized) {
        window.location.href = "/login?next=/checkout";
        return;
      }
      toast(result.error || T.error);
    });
  }

  function readStrategy() {
    try { return window.localStorage.getItem(STRATEGY_KEY) || ""; } catch (err) { return ""; }
  }

  function pickVariant(variants, strategy) {
    for (var i = 0; i < variants.length; i += 1) {
      if (variants[i].strategies.indexOf(strategy) !== -1) return variants[i];
    }
    return variants[0];
  }

  function drawSummary(host, variant) {
    var list = el("div", "quote-lines");
    variant.items.forEach(function (item) {
      var row = el("div", "quote-line");
      var left = el("div", "q-name");
      left.appendChild(el("div", null, item.name));
      left.appendChild(el("div", "q-qty", item.qty));
      row.appendChild(left);
      row.appendChild(el("div", "price", item.cost));
      list.appendChild(row);
    });
    host.appendChild(list);
    host.appendChild(totalRow(T.itemsTotal, variant.items_total));
    host.appendChild(totalRow(T.delivery, variant.delivery_total));
    host.appendChild(totalRow(T.grandTotal, variant.grand_total, true));
    if (variant.delivery_note) host.appendChild(el("p", "muted tiny", variant.delivery_note));
    host.appendChild(el("p", "muted tiny", variant.eta));
  }

  function initGeolocation() {
    var button = $("[data-detect]");
    if (!button) return;

    button.addEventListener("click", function () {
      if (!navigator.geolocation) { toast(T.detectFailed); return; }
      var original = button.textContent;
      button.disabled = true;
      button.textContent = T.detecting;

      navigator.geolocation.getCurrentPosition(async function (position) {
        var lat = position.coords.latitude;
        var lng = position.coords.longitude;
        $("[data-lat]").value = String(lat);
        $("[data-lng]").value = String(lng);

        try {
          var response = await fetch("/api/geocode?lat=" + lat + "&lng=" + lng);
          var data = await response.json();
          if (data.ok && data.address) $("[data-address-text]").value = data.address;
          if (data.notice) toast(data.notice);
        } catch (err) {
          toast(T.detectFailed);
        }
        button.disabled = false;
        button.textContent = original;
      }, function () {
        button.disabled = false;
        button.textContent = original;
        toast(T.detectFailed);
      }, { enableHighAccuracy: true, timeout: 10000 });
    });
  }

  function initAddressChoice() {
    var block = $("[data-new-address]");
    if (!block) return;
    function refresh() {
      var chosen = $$("[name='address_choice']").filter(function (node) { return node.checked; })[0];
      block.hidden = !!(chosen && chosen.value !== "new");
    }
    $$("[name='address_choice']").forEach(function (node) {
      node.addEventListener("change", refresh);
    });
    refresh();
  }

  /* ── Telegram Mini App ───────────────────────────────────────────── */

  function initTelegram() {
    var tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) return;
    try { tg.ready(); tg.expand(); } catch (err) { /* older clients */ }
    if (QB.authed || !tg.initData) return;

    postJSON("/auth/webapp", { init_data: tg.initData, next: window.location.pathname })
      .then(function (result) { if (result && result.ok) window.location.reload(); });
  }

  /* ── boot ────────────────────────────────────────────────────────── */

  document.addEventListener("DOMContentLoaded", function () {
    syncCount();
    initListForm();
    initQtyWidgets();
    initAddToBasket();
    initBasketPage();
    initAddressChoice();
    initCheckout();
    initTelegram();
  });
})();
