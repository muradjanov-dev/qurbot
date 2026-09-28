/* Restore the exact catalogue position when returning from a product card. */
(function () {
  "use strict";
  var prefix = "qb_catalog_scroll:";
  var restoreKey = "qb_catalog_restore";
  var current = window.location.pathname + window.location.search;

  document.addEventListener("click", function (event) {
    var product = event.target.closest("[data-catalog-product]");
    var back = event.target.closest("[data-catalog-return]");
    try {
      if (product) sessionStorage.setItem(prefix + current, String(window.scrollY));
      if (back) sessionStorage.setItem(restoreKey, back.getAttribute("href"));
    } catch (err) { /* storage unavailable */ }
  });

  function restore() {
    try {
      if (sessionStorage.getItem(restoreKey) !== current) return;
      sessionStorage.removeItem(restoreKey);
      var saved = Number(sessionStorage.getItem(prefix + current));
      if (Number.isFinite(saved) && saved >= 0) window.scrollTo(0, saved);
    } catch (err) { /* browser handles its own history restoration */ }
  }
  window.addEventListener("pageshow", restore);
})();

/* Refresh server-rendered catalogue regions while retaining purchase controls. */
(function () {
  "use strict";
  var root = document.querySelector('[data-live-root]');
  if (!root) return;
  var busy = false;
  var timer;
  var lastHTML = null;
  async function refresh() {
    if (document.hidden || busy) return;
    busy = true;
    try {
      var url = new URL(window.location.href);
      url.searchParams.set('fragment', '1');
      var response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(4500)});
      if (!response.ok) return;
      var html = await response.text();
      if (html === lastHTML) return;
      var documentFragment = new DOMParser().parseFromString(html, 'text/html');
      var next = documentFragment.querySelector('[data-live-root]');
      if (!next) return;
      lastHTML = html;
      root.querySelectorAll('[data-live-preserve]').forEach(function (control) {
        var placeholder = next.querySelector('[data-live-preserve="' + control.dataset.livePreserve + '"]');
        if (placeholder) {
          var oldUnit = control.querySelector('[data-product-unit]');
          var newUnit = placeholder.querySelector('[data-product-unit]');
          if (oldUnit && newUnit) oldUnit.textContent = newUnit.textContent;
          placeholder.replaceWith(control);
        }
      });
      root.replaceWith(next);
      root = next;
      var controls = root.querySelector('[data-live-preserve="purchase"]');
      if (controls) {
        var disabled = root.dataset.productActive === '0' || controls.dataset.productReady !== '1' || controls.dataset.productBusy === '1';
        controls.querySelectorAll('input, button').forEach(function (control) { control.disabled = disabled; });
      }
      document.dispatchEvent(new CustomEvent('qurbot:catalog-updated'));
    } catch (error) { /* Retain the current usable page on connection loss. */ }
    finally {busy = false;}
  }
  function schedule() {
    clearInterval(timer);
    if (!document.hidden) timer = setInterval(refresh, 5000);
  }
  document.addEventListener('visibilitychange', function () {schedule(); if (!document.hidden) refresh();});
  schedule();
})();
