/* Restore the exact catalogue position when returning from a product card. */
(function () {
  "use strict";
  var prefix = "qb_catalog_scroll:";
  var restoreKey = "qb_catalog_restore";
  var current = window.location.pathname + window.location.search;

  document.querySelectorAll("[data-catalog-product]").forEach(function (link) {
    link.addEventListener("click", function () {
      try { sessionStorage.setItem(prefix + current, String(window.scrollY)); } catch (err) { /* storage unavailable */ }
    });
  });

  document.querySelectorAll("[data-catalog-return]").forEach(function (link) {
    link.addEventListener("click", function () {
      try { sessionStorage.setItem(restoreKey, link.getAttribute("href")); } catch (err) { /* storage unavailable */ }
    });
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
