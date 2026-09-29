(function () {
  "use strict";

  var doc = document;
  var currencySelector = "[data-source-currency]";
  var amountSelector = "[data-source-amount]";

  function closest(node, selector) {
    return node && node.closest ? node.closest(selector) : null;
  }

  function addTier(button) {
    var form = closest(button, "form");
    if (!form) return;
    var list = form.querySelector("[data-tier-list]");
    var template = form.querySelector("template[data-tier-template]");
    if (!list || !template) return;
    var empty = list.querySelector("[data-tier-empty]");
    if (empty) empty.remove();
    list.appendChild(template.content.cloneNode(true));
  }

  function removeTier(button) {
    var row = closest(button, "[data-tier-row]");
    var form = closest(button, "form");
    if (!row || !form) return;
    var id = row.querySelector('input[name="tier_id"]');
    if (id && id.value) {
      var remove = doc.createElement("input");
      remove.type = "hidden";
      remove.name = "tier_remove_ids";
      remove.value = id.value;
      form.appendChild(remove);
    }
    var list = closest(row, "[data-tier-list]");
    row.remove();
    if (list && !list.querySelector("[data-tier-row]")) {
      var empty = doc.createElement("div");
      empty.className = "admin-tier-empty";
      empty.dataset.tierEmpty = "";
      empty.textContent = (window.QB && window.QB.admin_i18n && window.QB.admin_i18n.no_tiers) || "";
      list.appendChild(empty);
    }
  }

  function switchCurrency(select) {
    var initial = select.dataset.initialCurrency || select.value;
    if (initial === select.value) return;
    var priceBlock = closest(select, "[data-currency-price]");
    if (!priceBlock) return;
    var amount = priceBlock.querySelector(amountSelector);
    var confirmation = priceBlock.querySelector("[data-currency-confirm]");
    if (amount) {
      amount.value = "";
      amount.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (confirmation) confirmation.value = "true";
    select.dataset.initialCurrency = select.value;
    priceBlock.classList.add("currency-was-switched");
  }

  doc.addEventListener("change", function (event) {
    var target = event.target;
    if (target && target.matches && target.matches(currencySelector)) switchCurrency(target);
  });

  doc.addEventListener("click", function (event) {
    var add = closest(event.target, "[data-tier-add]");
    if (add) {
      event.preventDefault();
      addTier(add);
      return;
    }
    var remove = closest(event.target, "[data-tier-remove]");
    if (remove) {
      event.preventDefault();
      removeTier(remove);
    }
  });

})();

/* An image preview never navigates away from the current table or filters. */
(function () {
  'use strict';
  const dialog = document.querySelector('[data-image-dialog]');
  if (!dialog) return;
  const photo = dialog.querySelector('[data-image-full]');
  const title = dialog.querySelector('[data-image-title]');
  const status = dialog.querySelector('[data-image-status]');
  const original = dialog.querySelector('[data-image-original]');
  const close = dialog.querySelector('[data-image-close]');
  let opener = null;
  let previousOverflow = '';
  let pagePosition = {x: 0, y: 0};
  let tablePosition = null;
  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-image-preview]');
    if (!button) return;
    let url;
    try {url = new URL(button.dataset.imagePreview, location.href);} catch (_) {return;}
    if (!['http:', 'https:'].includes(url.protocol)) return;
    opener = button;
    pagePosition = {x: window.scrollX, y: window.scrollY};
    const table = button.closest('.admin-table-scroll');
    tablePosition = table ? {node: table, left: table.scrollLeft, top: table.scrollTop} : null;
    title.textContent = button.dataset.imageName || '';
    photo.alt = button.dataset.imageName || '';
    status.textContent = status.dataset.loading;
    status.hidden = false;
    photo.hidden = true;
    original.href = url.href;
    photo.onload = function () {status.hidden = true; photo.hidden = false;};
    photo.onerror = function () {status.textContent = status.dataset.error; photo.hidden = true;};
    photo.src = url.href;
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.showModal();
    close.focus({preventScroll: true});
  });
  close.addEventListener('click', function () {dialog.close();});
  dialog.addEventListener('click', function (event) {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  dialog.addEventListener('close', function () {
    document.body.style.overflow = previousOverflow;
    photo.onload = null; photo.onerror = null; photo.removeAttribute('src');
    if (opener?.isConnected) opener.focus({preventScroll: true});
    if (tablePosition?.node.isConnected) {
      tablePosition.node.scrollLeft = tablePosition.left;
      tablePosition.node.scrollTop = tablePosition.top;
    }
    window.scrollTo(pagePosition.x, pagePosition.y);
  });
})();
