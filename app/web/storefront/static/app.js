/* QurBot storefront.
 *
 * Guests keep a local draft; signed-in customers share a durable bot/web cart.
 * Nothing here
 * decides a price -- every total on screen came back from the server, which
 * recomputes it from live offers and ignores anything this file claims.
 */
(function () {
  "use strict";

  var QB = window.QB || { lang: "uz_latn", authed: false, i18n: {} };
  var T = QB.i18n || {};
  var STORE_KEY = "qb_basket_v1";
  var STRATEGY_KEY = "qb_strategy";
  var CHECKOUT_DRAFT_KEY = "qb_checkout_restore_v1";
  var cartRevision = 0;
  var cartLines = [];
  var legacyCartLines = [];
  var legacyCartStorageValue = null;
  var legacyCartReviewMessage = "";
  var cartBusy = false;
  var csrf = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = csrf ? csrf.content : "";
  var draftKey = "qb_draft_" + csrfToken;

  function requestKey() { return crypto.randomUUID(); }

  function quantityUnits(value) {
    var text = String(value).trim().replace(",", ".");
    if (!/^\d+(?:\.\d{1,6})?$/.test(text)) return null;
    var parts = text.split(".");
    return BigInt(parts[0]) * 1000000n + BigInt((parts[1] || "").padEnd(6, "0"));
  }

  function quantityText(units) {
    var digits = units.toString().padStart(7, "0");
    return (digits.slice(0, -6) + "." + digits.slice(-6)).replace(/\.?0+$/, "");
  }

  function stepQuantity(value, step, min) {
    var current = quantityUnits(value);
    var next = (current === null ? 1000000n : current) + BigInt(step) * 1000000n;
    var floor = quantityUnits(min) || 0n;
    return quantityText(next < floor ? floor : next);
  }

  async function cartRequest(url, method, body) {
    try {
      var response = await fetch(url, {
        method: method || "GET",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: body === undefined ? undefined : JSON.stringify(body)
      });
      var result = await response.json();
      if (!response.ok) result.ok = false;
      return result;
    } catch (err) { return { ok: false, error: T.error }; }
  }

  function acceptCart(result, drafts) {
    if (result.revision < cartRevision) return;
    cartRevision = result.revision;
    cartLines = result.lines.concat(drafts || []);
    cartLines.forEach(function (line, index) { line.line_no = index + 1; });
    try { sessionStorage.setItem(draftKey, JSON.stringify(drafts || [])); } catch (err) { /* memory draft */ }
    syncCount();
  }

  function readLegacyCart() {
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return { raw: raw, lines: Array.isArray(parsed) ? parsed : [] };
    } catch (err) { return { raw: null, lines: [] }; }
  }

  function clearLegacyCart(raw) {
    try {
      if (window.localStorage.getItem(STORE_KEY) !== raw) return false;
      window.localStorage.removeItem(STORE_KEY);
      window.localStorage.removeItem("qb_cart_merge_key");
      return true;
    } catch (err) { return false; }
  }

  function durableMergeKey() {
    try {
      var stored = window.localStorage.getItem("qb_cart_merge_key");
      if (stored) return stored;
      var created = requestKey();
      window.localStorage.setItem("qb_cart_merge_key", created);
      return created;
    } catch (err) { return null; }
  }

  function hasCartSnapshot(result) {
    return result && Number.isInteger(result.revision) && Array.isArray(result.lines);
  }

  async function loadCart() {
    if (!QB.authed) return true;
    var result = await cartRequest("/api/cart");
    if (!result.ok) { toast(result.error || T.error); return false; }
    var drafts = [];
    try { drafts = JSON.parse(sessionStorage.getItem(draftKey) || "[]"); } catch (err) { /* empty draft */ }
    acceptCart(result, Array.isArray(drafts) ? drafts : []);
    var stored = readLegacyCart();
    var guest = stored.lines;
    legacyCartLines = [];
    legacyCartStorageValue = stored.raw;
    legacyCartReviewMessage = "";
    if (!Array.isArray(guest) || !guest.length) return true;
    var mergeKey = durableMergeKey();
    if (!mergeKey) {
      legacyCartLines = guest;
      legacyCartStorageValue = stored.raw;
      legacyCartReviewMessage = "failed";
      return true;
    }
    var merged = await cartRequest("/api/cart/merge", "POST", {
      lines: basket.payload(guest), merge_key: mergeKey, expected_revision: cartRevision
    });
    if (!merged.ok) {
      legacyCartLines = guest;
      legacyCartStorageValue = stored.raw;
      legacyCartReviewMessage = merged.code === "unit_conflict" ? "conflict" : "failed";
      if (hasCartSnapshot(merged)) {
        acceptCart(merged, drafts);
      } else {
        var fresh = await cartRequest("/api/cart");
        if (fresh.ok) acceptCart(fresh, drafts);
      }
      return true;
    }
    acceptCart(merged, drafts.concat(guest.filter(function (line) { return !line.canonical_id; })));
    if (clearLegacyCart(stored.raw)) {
      legacyCartLines = [];
      legacyCartStorageValue = null;
      legacyCartReviewMessage = "";
    } else {
      var changed = readLegacyCart();
      legacyCartLines = changed.lines;
      legacyCartStorageValue = changed.raw;
      legacyCartReviewMessage = changed.lines.length ? "changed" : "";
    }
    return true;
  }

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
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify(body || {})
    });
    try {
      var result = await response.json();
      if (response.status === 401) {
        result.ok = false;
        result.error = result.error || T.loginRequired;
        result.unauthorized = true;
      } else if (!response.ok) result.ok = false;
      return result;
    } catch (err) {
      return {
        ok: false,
        error: response.status === 401 ? T.loginRequired : T.error,
        unauthorized: response.status === 401
      };
    }
  }

  /* ── basket store ────────────────────────────────────────────────── */

  var basket = {
    load: function () {
      if (QB.authed) {
        var copy = JSON.parse(JSON.stringify(cartLines));
        Object.defineProperty(copy, "cartRevision", {value: cartRevision});
        return copy;
      }
      try {
        var raw = window.localStorage.getItem(STORE_KEY);
        var parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        return [];
      }
    },
    save: async function (lines, expectedRevision) {
      if (QB.authed) {
        if (cartBusy) { toast(T.loading); return false; }
        var baseRevision = expectedRevision === undefined ? lines.cartRevision : expectedRevision;
        if (baseRevision !== undefined && baseRevision !== cartRevision) {
          toast(T.error);
          renderBasket();
          return false;
        }
        cartBusy = true;
        try {
          var wanted = new Map();
          basket.orderable(lines).forEach(function (line) { wanted.set(line.canonical_id, line); });
          var previous = new Map();
          basket.orderable(cartLines).forEach(function (line) { previous.set(line.canonical_id, line); });
          var result = { ok: true, revision: cartRevision, lines: basket.orderable(cartLines) };
          for (var entry of previous) {
            if (!wanted.has(entry[0])) {
              result = await cartRequest("/api/cart/items/" + entry[0] + "?expected_revision=" + result.revision, "DELETE");
              if (!result.ok) throw result;
            }
          }
          for (var item of wanted) {
            var old = previous.get(item[0]);
            if (!old || old.qty !== item[1].qty || old.unit_code !== item[1].unit_code) {
              result = await cartRequest("/api/cart/items/" + item[0], "PUT", {
                qty: String(item[1].qty), unit_code: item[1].unit_code, expected_revision: result.revision
              });
              if (!result.ok) throw result;
            }
          }
          acceptCart(result, lines.filter(function (line) { return !line.canonical_id; }));
          return true;
        } catch (err) {
          var fresh = await cartRequest("/api/cart");
          if (fresh.ok) acceptCart(fresh, cartLines.filter(function (line) { return !line.canonical_id; }));
          toast(err.error || T.error);
          renderBasket();
          return false;
        } finally { cartBusy = false; }
      }
      try {
        window.localStorage.setItem(STORE_KEY, JSON.stringify(lines));
        window.localStorage.removeItem("qb_cart_merge_key");
      } catch (err) { /* private mode: the basket is then per-page, still usable */ }
      syncCount();
      return true;
    },
    clear: function () { return basket.save([]); },
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

  document.addEventListener("submit", function (event) {
    var prompt = event.target.dataset?.confirm;
    if (prompt && !window.confirm(prompt)) event.preventDefault();
  });

  /* ── product page: add to basket ─────────────────────────────────── */

  function initQtyWidgets() {
    $$("[data-qty]").forEach(function (widget) {
      var input = $("input", widget);
      $$("button", widget).forEach(function (button) {
        button.addEventListener("click", function () {
          input.value = stepQuantity(input.value, button.dataset.step || "1", input.min || "1");
        });
      });
    });
  }

  function initAddToBasket() {
    var button = $("[data-add-product]");
    if (!button) return;

    button.addEventListener("click", async function () {
      if (button.closest("[data-live-root]")?.dataset.productActive === "0") return;
      var qtyInput = $("[data-qty] input");
      var lines = basket.load();
      button.disabled = true;
      var purchase = button.closest("[data-live-preserve]");
      if (purchase) purchase.dataset.productBusy = "1";
      var result = await postJSON("/api/basket/product", {
        canonical_id: Number(button.dataset.addProduct),
        qty: qtyInput ? qtyInput.value : "1",
        line_no: basket.nextNo(lines) + 1
      });
      if (purchase) purchase.dataset.productBusy = "0";
      button.disabled = button.closest("[data-live-root]")?.dataset.productActive === "0";

      if (!result.ok) { toast(result.error || T.error); return; }
      var existing = lines.find(function (line) { return line.canonical_id === result.line.canonical_id; });
      if (existing) {
        if (existing.unit_code !== result.line.unit_code) { toast(T.error); return; }
        existing.qty = result.line.qty;
      } else {
        lines.push(result.line);
      }
      if (!await basket.save(lines)) return;
      var feedback = $('[data-product-added]');
      if (feedback) feedback.textContent = (result.line.canonical_name || result.line.parsed_name) + ' — ' + result.line.qty + ' ' + result.line.unit_code + '. ' + T.added;
      toast(T.added);
    });
    var active = button.closest("[data-live-root]")?.dataset.productActive !== "0";
    var preserved = button.closest("[data-live-preserve]");
    if (preserved) preserved.dataset.productReady = "1";
    button.disabled = !active;
    $$("[data-qty] input, [data-qty] button").forEach(function (control) { control.disabled = !active; });
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
    remove.addEventListener("click", async function () {
      lines.splice(index, 1);
      await basket.save(lines);
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

    async function commit(value) {
      var parsed = quantityUnits(value);
      if (parsed === null || parsed <= 0n) { input.value = String(line.qty); return; }
      line.qty = quantityText(parsed);
      input.value = line.qty;
      await basket.save(lines);
      renderBasket();
    }
    minus.addEventListener("click", function () { commit(stepQuantity(line.qty, "-1", "0")); });
    plus.addEventListener("click", function () { commit(stepQuantity(line.qty, "1", "0")); });
    input.addEventListener("change", function () { commit(input.value); });

    qty.appendChild(minus);
    qty.appendChild(input);
    qty.appendChild(plus);
    actions.appendChild(qty);
    actions.appendChild(el("span", "muted tiny", line.unit_code || ""));
    wrap.appendChild(actions);

    if (line.status !== "ok" && line.clarify_question) {
      wrap.appendChild(el("p", "muted tiny", line.clarify_question));
    }
    if (line.status === "choose" && line.candidates && line.candidates.length) {
      var options = el("div", "chips");
      line.candidates.forEach(function (candidate) {
        var chip = el("button", "chip", candidate.price ? candidate.name + " · " + candidate.price : candidate.name);
        chip.type = "button";
        chip.addEventListener("click", async function () {
          line.status = "ok";
          line.canonical_id = candidate.canonical_id;
          line.canonical_name = candidate.name;
          line.candidates = [];
          await basket.save(lines);
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
        if (!await basket.save(lines.concat(result.lines), lines.cartRevision)) return;
        field.value = "";
        addForm.hidden = true;
        renderBasket();
      });
    }

    var clear = $("[data-clear]");
    if (clear) {
      clear.addEventListener("click", async function () {
        await basket.clear();
        renderBasket();
        $("[data-quote]").innerHTML = "";
      });
    }

    var calc = $("[data-calculate]");
    if (calc) calc.addEventListener("click", function () { runQuote(calc); });
  }

  async function initLegacyCartReview() {
    var card = $("[data-local-cart-review]");
    if (!card || !QB.authed) return;
    var lineList = $("[data-local-cart-draft]", card);
    var message = $("[data-local-cart-message]", card);
    var retry = $("[data-retry-local-cart]", card);
    var drop = $("[data-drop-local-cart]", card);
    var labels = {
      drop: card.dataset.dropLabel || "",
      failed: card.dataset.reviewFailed || T.error,
      conflict: card.dataset.reviewConflict || card.dataset.reviewFailed || T.error,
      changed: card.dataset.reviewChanged || card.dataset.reviewFailed || T.error,
      retrying: card.dataset.reviewRetrying || T.loading,
      discarded: card.dataset.reviewDiscarded || "",
      storageFailed: card.dataset.reviewStorageFailed || T.error
    };

    function selectedIndexes() {
      return $$('input[data-drop-local-index]:checked', lineList).map(function (input) {
        var index = Number(input.value);
        return Number.isSafeInteger(index) && index >= 0 ? index : -1;
      }).filter(function (index) { return index >= 0; });
    }

    function updateDropState() {
      drop.disabled = selectedIndexes().length === 0;
    }

    function renderDraft() {
      card.hidden = legacyCartLines.length === 0;
      lineList.replaceChildren();
      legacyCartLines.forEach(function (line, index) {
        var item = document.createElement("li");
        var label = document.createElement("label");
        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.dataset.dropLocalIndex = "";
        checkbox.value = String(index);
        checkbox.addEventListener("change", updateDropState);
        var name = line.canonical_name || line.parsed_name || line.raw_text || (line.canonical_id ? "#" + line.canonical_id : "");
        var quantity = [line.qty, line.unit_code].filter(Boolean).join(" ");
        var text = document.createElement("span");
        text.textContent = [name, quantity].filter(Boolean).join(" — ");
        label.append(checkbox, text);
        label.append(document.createTextNode(" — " + labels.drop));
        item.append(label);
        lineList.append(item);
      });
      message.textContent = legacyCartReviewMessage === "changed"
        ? labels.changed
        : legacyCartReviewMessage === "conflict" ? labels.conflict
        : legacyCartReviewMessage === "discarded" ? labels.discarded
        : legacyCartReviewMessage ? labels.failed : "";
      retry.disabled = legacyCartLines.length === 0;
      updateDropState();
    }

    async function retryMerge() {
      if (!legacyCartLines.length) return;
      retry.disabled = true;
      drop.disabled = true;
      message.textContent = labels.retrying;

      // A prior 409 may have advanced the server cart; always use a fresh revision.
      var fresh = await cartRequest("/api/cart");
      if (!fresh.ok) {
        legacyCartReviewMessage = "failed";
        message.textContent = labels.failed;
        retry.disabled = false;
        updateDropState();
        return;
      }
      var drafts = cartLines.filter(function (line) { return !line.canonical_id; });
      acceptCart(fresh, drafts);
      renderBasket();

      var stored = readLegacyCart();
      if (stored.raw !== legacyCartStorageValue) {
        legacyCartLines = stored.lines;
        legacyCartStorageValue = stored.raw;
        legacyCartReviewMessage = "changed";
        renderDraft();
        return;
      }
      var guest = stored.lines;
      if (!guest.length) {
        legacyCartLines = [];
        legacyCartReviewMessage = "";
        renderDraft();
        return;
      }

      var mergeKey = durableMergeKey();
      if (!mergeKey) {
        legacyCartReviewMessage = "failed";
        message.textContent = labels.failed;
        retry.disabled = false;
        updateDropState();
        return;
      }
      var merged = await cartRequest("/api/cart/merge", "POST", {
        lines: basket.payload(guest), merge_key: mergeKey, expected_revision: cartRevision
      });
      if (!merged.ok) {
        legacyCartLines = guest;
        legacyCartStorageValue = stored.raw;
        legacyCartReviewMessage = merged.code === "unit_conflict" ? "conflict"
          : merged.code === "cart_conflict" ? "changed" : "failed";
        if (hasCartSnapshot(merged)) {
          acceptCart(merged, drafts);
        } else {
          var current = await cartRequest("/api/cart");
          if (current.ok) acceptCart(current, drafts);
        }
        renderBasket();
        message.textContent = legacyCartReviewMessage === "conflict" ? labels.conflict
          : legacyCartReviewMessage === "changed" ? labels.changed : labels.failed;
        retry.disabled = false;
        updateDropState();
        return;
      }

      acceptCart(merged, drafts.concat(guest.filter(function (line) { return !line.canonical_id; })));
      if (clearLegacyCart(stored.raw)) {
        legacyCartLines = [];
        legacyCartStorageValue = null;
        legacyCartReviewMessage = "";
      } else {
        var changed = readLegacyCart();
        legacyCartLines = changed.lines;
        legacyCartStorageValue = changed.raw;
        legacyCartReviewMessage = changed.lines.length ? "changed" : "";
      }
      renderBasket();
      renderDraft();
    }

    function discardSelected() {
      var selected = selectedIndexes();
      if (!selected.length) return;
      var stored = readLegacyCart();
      if (stored.raw !== legacyCartStorageValue) {
        legacyCartLines = stored.lines;
        legacyCartStorageValue = stored.raw;
        legacyCartReviewMessage = "changed";
        renderDraft();
        return;
      }
      var remove = new Set(selected);
      var remaining = legacyCartLines.filter(function (_, index) { return !remove.has(index); });
      try {
        if (remaining.length) {
          window.localStorage.setItem(STORE_KEY, JSON.stringify(remaining));
        } else {
          window.localStorage.removeItem(STORE_KEY);
          window.localStorage.removeItem("qb_cart_merge_key");
        }
      } catch (err) {
        legacyCartReviewMessage = "storage_failed";
        message.textContent = labels.storageFailed;
        updateDropState();
        return;
      }
      legacyCartLines = remaining;
      legacyCartStorageValue = remaining.length ? JSON.stringify(remaining) : null;
      legacyCartReviewMessage = remaining.length ? "discarded" : "";
      renderDraft();
    }

    retry.addEventListener("click", retryMerge);
    drop.addEventListener("click", discardSelected);
    renderDraft();
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
    if (result.requires_confirmation) { window.location.href = '/chat?cart=1'; return; }

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
    meta.textContent = variant.coverage;
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
      link.download = "tezqur-taklif.pdf";
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

  function readCheckoutDraft() {
    try {
      var draft = JSON.parse(sessionStorage.getItem(CHECKOUT_DRAFT_KEY) || "null");
      sessionStorage.removeItem(CHECKOUT_DRAFT_KEY);
      return draft && typeof draft === "object" ? draft : null;
    } catch (err) { return null; }
  }

  function saveCheckoutDraft() {
    try {
      var selected = $$('[name="address_choice"]').filter(function (node) { return node.checked; })[0];
      sessionStorage.setItem(CHECKOUT_DRAFT_KEY, JSON.stringify({
        phone: $("[data-phone]")?.value || "",
        address_choice: selected ? selected.value : "new",
        address_text: $("[data-address-text]")?.value || "",
        district: $("[data-district]")?.value || "",
        lat: $("[data-lat]")?.value || "",
        lng: $("[data-lng]")?.value || "",
        comment: $("[data-comment]")?.value || ""
      }));
    } catch (err) { /* The customer can still sign in and use the saved cart. */ }
  }

  function restoreCheckoutDraft() {
    var draft = readCheckoutDraft();
    if (!draft) return;
    if ($("[data-phone]")) $("[data-phone]").value = draft.phone || "";
    if ($("[data-address-text]")) $("[data-address-text]").value = draft.address_text || "";
    if ($("[data-district]")) $("[data-district]").value = draft.district || "";
    if ($("[data-lat]")) $("[data-lat]").value = draft.lat || "";
    if ($("[data-lng]")) $("[data-lng]").value = draft.lng || "";
    if ($("[data-comment]")) $("[data-comment]").value = draft.comment || "";
    var choice = $$('[name="address_choice"]').filter(function (node) {
      return node.value === (draft.address_choice || "new");
    })[0];
    if (choice) choice.checked = true;
  }

  async function initGuestCartClaimReview() {
    var card = $("[data-guest-cart-review]");
    if (!card) return;
    var lineList = $("[data-guest-cart-source]", card);
    var message = $("[data-guest-claim-message]", card);
    var retry = $("[data-retry-guest-claim]", card);
    var drop = $("[data-drop-guest-claim]", card);
    var previewLabels = {
      loading: card.dataset.previewLoading || T.loading,
      empty: card.dataset.previewEmpty || T.error,
      failed: card.dataset.previewFailed || T.error,
      drop: card.dataset.dropLabel || "",
      confirm: card.dataset.confirmLabel || ""
    };

    function selectedIds() {
      return $$('input[data-drop-guest-id]:checked', lineList).map(function (input) {
        return Number(input.value);
      }).filter(function (id) { return Number.isSafeInteger(id) && id > 0; });
    }

    function updateDropState() {
      drop.disabled = selectedIds().length === 0;
    }

    function renderSourceLines(lines) {
      lineList.replaceChildren();
      lines.forEach(function (line) {
        var item = document.createElement("li");
        var label = document.createElement("label");
        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.dataset.dropGuestId = "";
        checkbox.value = String(line.canonical_id);
        checkbox.addEventListener("change", updateDropState);
        var text = document.createElement("span");
        text.textContent = String(line.name || ("#" + line.canonical_id)) +
          " — " + String(line.qty) + " " + String(line.unit_code);
        label.append(checkbox, text);
        label.append(document.createTextNode(" — " + previewLabels.drop));
        item.append(label);
        if (line.requires_confirmation) {
          var note = document.createElement("small");
          note.textContent = previewLabels.confirm;
          item.append(note);
        }
        lineList.append(item);
      });
      updateDropState();
    }

    async function loadPreview() {
      message.textContent = previewLabels.loading;
      var result = await cartRequest("/api/cart/claim-guest", "GET");
      if (!result.ok) {
        message.textContent = result.error || previewLabels.failed;
        return false;
      }
      if (result.status === "none") {
        card.hidden = true;
        return false;
      }
      var lines = Array.isArray(result.source_lines) ? result.source_lines : [];
      renderSourceLines(lines);
      message.textContent = lines.length ? "" : previewLabels.empty;
      retry.disabled = false;
      return true;
    }

    async function resolveClaim(payload) {
      retry.disabled = true;
      drop.disabled = true;
      var result = await cartRequest("/api/cart/claim-guest", "POST", payload);
      if (result.ok) {
        window.location.replace("/basket");
        return;
      }
      message.textContent = result.error || T.error;
      retry.disabled = false;
      await loadPreview();
      updateDropState();
    }

    retry.disabled = true;
    drop.disabled = true;
    retry.addEventListener("click", function () {
      void resolveClaim({});
    });
    drop.addEventListener("click", function () {
      var ids = selectedIds();
      if (ids.length) void resolveClaim({drop_guest_ids: ids});
    });
    await loadPreview();
  }

  function initCheckout() {
    var root = $("[data-checkout]");
    if (!root) return;

    var strategy = root.dataset.strategy || readStrategy();
    var summary = $("[data-order-summary]");
    var confirm = $("[data-confirm]");
    restoreCheckoutDraft();
    var expectedTotal = null;
    var checkoutRevision = cartRevision;
    var checkoutKey = requestKey();
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
      if (expectedTotal === null || cartBusy) { toast(T.loading); return; }
      var phone = $("[data-phone]").value.trim();
      if (!phone) { toast(T.phoneRequired); return; }

      var chosen = $$("[name='address_choice']").filter(function (node) { return node.checked; })[0];
      var body = {
        lines: payload,
        strategy: strategy,
        phone: phone,
        comment: $("[data-comment]").value.trim(),
        expected_total: expectedTotal,
        cart_revision: checkoutRevision,
        idempotency_key: checkoutKey
      };

      if (chosen && chosen.value !== "new") {
        body.address_id = Number(chosen.value);
      } else {
        var text = $("[data-address-text]").value.trim();
        if (!text) { toast(T.addressRequired); return; }
        body.address_text = text;
        var district = $("[data-district]")?.value;
        if (district) body.district_id = Number(district);
        var lat = $("[data-lat]").value;
        var lng = $("[data-lng]").value;
        if (lat && lng) { body.lat = Number(lat); body.lng = Number(lng); }
        else if (!district) { toast(T.districtRequired); return; }
      }

      confirm.disabled = true;
      var original = confirm.textContent;
      confirm.textContent = T.loading;
      var result = await postJSON("/api/order", body);
      confirm.disabled = false;
      confirm.textContent = original;

      if (result.ok) {
        // The server removed exactly the ordered products atomically.
        window.location.href = result.redirect || "/orders";
        return;
      }
      if (result.price_changed && result.variant) {
        checkoutKey = requestKey();
        expectedTotal = result.variant.grand_total_raw;
        summary.innerHTML = "";
        drawSummary(summary, result.variant);
      }
      if (result.code === "cart_conflict") {
        toast(result.error || T.error);
        window.location.href = "/basket";
        return;
      }
      if (result.unauthorized) {
        saveCheckoutDraft();
        var next = window.location.pathname + window.location.search;
        window.location.href = "/login?next=" + encodeURIComponent(next) + "&msg=web_checkout_login_required";
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

  /* ── boot ────────────────────────────────────────────────────────── */

  document.addEventListener("qurbot:cart-updated", function (event) {
    if (QB.authed && event.detail && event.detail.ok) {
      acceptCart(event.detail, cartLines.filter(function (line) { return !line.canonical_id; }));
      renderBasket();
    }
  });

  document.addEventListener("visibilitychange", async function () {
    if (!QB.authed || document.hidden || cartBusy) return;
    var fresh = await cartRequest("/api/cart");
    if (fresh.ok) {
      acceptCart(fresh, cartLines.filter(function (line) { return !line.canonical_id; }));
      renderBasket();
    }
  });

  document.addEventListener("DOMContentLoaded", async function () {
    if (window.QB.ready && !await window.QB.ready) return;
    if (!await loadCart()) return;
    await initGuestCartClaimReview();
    await initLegacyCartReview();
    syncCount();
    initQtyWidgets();
    initAddToBasket();
    initBasketPage();
    initAddressChoice();
    initCheckout();
  });
})();
