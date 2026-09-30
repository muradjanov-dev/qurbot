# Tezqur Delivery Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Correct verified end-to-end delivery defects without changing the approved business model.

**Architecture:** Keep checkout and admin edits in the existing transactional services. Repair the contracts between workflow events, Telegram transport, versioned callbacks, and privacy-safe web projections; preserve carts across failed authentication-time merges.

**Tech Stack:** Python 3.12, FastAPI/Jinja, SQLAlchemy/PostgreSQL, aiogram/arq, browser JavaScript, pytest/Playwright.

**Spec:** `docs/SPEC.md` §4.3 and the Order flow; the user's approved delivery plan and request to audit/fix the deployed system.

## Global Constraints

- One logical Tezqur house shop; no supplier routing or courier account/panel.
- Admin-only `new → confirmed → collecting → in_transit → fulfilled`; active cancellation requires a reason, corrections retain private audit reasons.
- Courier name and phone gate departure. Internal courier cost never changes quoted customer totals.
- Status, immutable history, and outbox persist in one transaction; stale versions cannot overwrite a newer admin action.
- Customer pages expose only the customer's orders and public status/contact history, never internal notes/costs/correction reasons.
- Telegram retries follow 30 seconds, 2, 10, and 30 minutes after failure and honor `retry_after`; preserve per-order/recipient FIFO and cleanup protection.
- Guest merge uses maximum quantity, not addition; unsuccessful resolution preserves both sources.
- All subagents use `gpt-6-luna`, `max`; the parent independently verifies integration.
- Test fixtures use isolated databases/dummy Telegram credentials. Production access for investigation is read-only.
- Prior release authorization remains: checked commits go to production `master` through existing CI/deploy, no PR; backup precedes migration/deploy.

## Review Focus

1. Producer/consumer mismatch must not suppress departure and block delivered updates (Task 1).
2. Slow transport responses must not shorten post-failure retry waits (Task 1).
3. Old Telegram callbacks after a correction back to `new` must not reconfirm (Task 2).
4. Long or historical order records must not hide actionable notification failures or offer impossible edits (Task 3).
5. Failed localStorage cart imports must remain visible and resolvable without resurrecting completed carts (Task 4).

### Task 1: Telegram delivery contract and result-time retries

**Files:** `app/services/order_notification_service.py`; `tests/integration/test_order_notification_delivery.py`.
**Interfaces:** Consumes workflow-produced `customer_departure` and existing leased outbox rows; preserves `deliver_order_notifications(session, bot, now=..., limit=...)`, with a controlled clock seam if required.

- [x] RED: normal workflow queues confirmed, collecting, departure, fulfilled; worker must send all four FIFO with courier contact on the third. Unknown kinds remain failed without sends. Observed 2/4 at deployed baseline.
- [x] RED: controlled clock advances while Telegram raises RetryAfter/transient error; available time must equal result time plus the specified wait.
- [x] GREEN: recognize departure and use transport-result timestamps.
- [x] Verify focused delivery tests, Ruff/mypy and PostgreSQL overlap test; commit `bc220e9`.
- [x] Independent task review.

### Task 2: Versioned and localized Telegram decisions

**Files:** Shared parsing in `app/bot/order_callbacks.py`; order decision portions of `app/bot/handlers/admin.py`, `app/bot/handlers/shop.py`, `app/bot/keyboards/inline.py`; keyboard call sites in `app/services/order_workflow.py`, `app/workers/tasks.py`, and the missing-markup fallback in `app/services/order_notification_service.py`; scoped bot/keyboard/workflow/worker tests and `app/core/order_delivery_i18n.py` localized copy.
**Interfaces:** Confirmation callback carries order/part ID plus workflow revision; legacy callbacks without a revision mean revision zero. All producers use the actual current revision. Cancellation continues opening the web form for a real reason. Existing language values are `uz_latn`, `uz_cyrl`, `ru`.

- [x] RED: original callback after confirm then correction back to new rejects; order remains new and event/outbox counts do not increase.
- [x] GREEN: strict compatible callback parsing, revision checks and every producer passing the correct revision.
- [x] RED/GREEN: Russian/Cyrillic primary order buttons and decision feedback use their requested language, with no hard-coded Latin fallback in normal supported-language cases.
- [x] RED/GREEN: missing stored markup uses fresh current revision and recipient language; a non-new order offers only a safe detail link and malformed markup remains failed.
- [x] RED/GREEN: a customer address containing HTML metacharacters appears literally in the reminder payload; escape untrusted fields while retaining trusted formatting.
- [x] RED/GREEN: blocked/test recipients receive no private reminder; refresh current identity before sending, preserve configured-ID authority, and record no sent marker when no send succeeds.
- [x] Verify callbacks, keyboard, workflow and reminder integration; commit and independent review.

### Task 3: Safe, actionable web delivery history

**Files:** Order sections of `app/web/storefront/routers/manage.py`; `routers/orders.py`; `manage_order_detail.html`, `manage_orders.html`, `order_detail.html`; `app/core/fulfillment_ui_i18n.py`; scoped fulfillment web tests.
**Interfaces:** Consume `public_order_event()`'s existing `public_contact` snapshot. Current-house capability is separate from historical read visibility; service authorization remains authoritative.

- [x] RED: two in-transit courier changes retain each public name/phone snapshot in detail history, while private details stay absent.
- [x] GREEN: preserve and render the safe contact DTO; current courier card remains current.
- [x] RED: old failed FIFO head plus over 100 later notification rows stays discoverable and retryable.
- [x] GREEN: expose actionable failed heads independently of the recent-history limit; retain bounded recent rows without silently hiding failures.
- [x] RED: retired-partner/no-part historical order renders a clear read-only view with no mutation forms; current-house order remains editable.
- [x] GREEN: capability-aware admin view/list badge; preserve historical order/price data and backend rejections.
- [x] Verify relevant web integration, compile/templates, Ruff/mypy; commit and independent review.

### Task 4: Recover legacy localStorage cart conflicts

**Files:** Local cart import/review portions of `app/web/storefront/static/app.js`; `templates/basket.html`; `app/core/guest_claim_i18n.py`; scoped executable JavaScript/browser and cart tests. No auth/checkout/model changes unless separately verified necessary.
**Interfaces:** Existing `qb_basket_v1`, `/api/cart`, `/api/cart/merge` and max-quantity server merge. Cookie-owned server guest review remains intact.

- [x] RED: authenticated server cart plus incompatible localStorage guest line fails merge; retained local lines must remain visible and recoverable.
- [x] GREEN: explicit local-draft review/retry/drop, preserving storage until successful merge or explicit user discard; refresh stale server revision before retry.
- [x] Verify success, repeated retry, transient failure and completed-order non-resurrection using real browser code; copy remains in all three languages.
- [x] Scoped tests and independent review; commit only owned files.

### Task 5: Integration and release

- [ ] Review each completed task's spec compliance and code quality, then one whole-branch review against baseline `f23ecd4`.
- [ ] Run `make check`, isolated PostgreSQL migration/concurrency checks, Mini App authentication regression, desktop/mobile staging checks.
- [ ] Inspect production for known departure rows failed by the old allowlist; any recovery must be limited to actual affected rows, audited and authorized by the existing status notification behavior.
- [ ] Take a fresh production backup; fast-forward checked commits to master, no PR.
- [ ] Verify CI/deploy, web/worker SHA, `/ready`, migration head, unchanged historical price snapshots and functioning worker schedule. Report fixes and verified architectural limits.
