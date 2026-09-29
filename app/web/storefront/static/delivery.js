(() => {
  "use strict";

  document.querySelectorAll("[data-status-form]").forEach((form) => {
    const status = form.querySelector("[data-status-target]");
    const reason = form.querySelector("[data-cancel-reason]");
    if (!status || !reason) return;

    const updateReason = () => {
      const required = status.value === "cancelled";
      reason.required = required;
      reason.setAttribute("aria-required", required ? "true" : "false");
    };
    status.addEventListener("change", updateReason);
    updateReason();
  });
})();
