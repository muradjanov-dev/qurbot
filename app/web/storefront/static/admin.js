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
