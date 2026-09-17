# Shared cart and checkout

Migration `0017_unified_cart` follows `0016_order_delivery_pin`. It adds `carts`,
`cart_items`, `cart_merges`, `checkout_attempts`, and `orders.is_test`. Cart rows
are live state; ordered baskets and quote snapshots remain immutable history.

`CartService(session)` exposes `get(user_id)`, `set_item(user_id, product_id, qty,
expected_revision=..., unit_code=...)`, `remove_item`, `clear`, `merge`, and
`migrate_legacy(user_id, fsm_data)`. Methods return `CartSnapshot(revision, lines)`;
`payload()` returns `{ok, revision, lines}`. Callers own commit/rollback. Each
transaction locks the user's cart row before inspecting a revision or changing
items. Quantity strings retain their units and up to six decimal places.

Authenticated HTTP endpoints:

- `GET /api/cart`
- `PUT /api/cart/items/{product_id}` with `{qty, unit_code?, expected_revision}`
- `DELETE /api/cart/items/{product_id}?expected_revision=N`
- `POST /api/cart/merge` with `{lines, merge_key, expected_revision}`

Writes require the session-bound `X-CSRF-Token`. Revision conflicts return HTTP
409 and the current snapshot; invalid items return 422. Clients must refresh and
let the customer reconcile a conflict. They must not automatically replay stale
quantities over new state. Authenticated lines come from the server; guests keep
local drafts. Merge takes the maximum quantity for a product in the same unit.
Durable receipts prevent a retry from restoring products deleted after a merge.
Legacy FSM and agent sources each have a one-time receipt, including empty sources.

`POST /api/order` requires CSRF, `cart_revision`, `idempotency_key`, a finite
decimal-string `expected_total`, phone and delivery details. It orders the server
cart, revalidates products and live offers, and returns `price_changed` with the
new variant when the total changes. Client-supplied lines do not determine the
order. Keep the key stable when retrying an uncertain response; use a new key
after the customer changes the checkout or accepts a repriced quote. A successful
retry returns the same order without another reward or notification. An altered
request using a successful key returns 409. Order, reward, receipt, and removal
of ordered products commit together. The bot retains unavailable products from
a partial quote in the cart and requires reconfirmation when live pricing changes.

Test accounts are configured through `settings.test_tg_ids`. Orders record
`is_test` at creation. They remain visible to their customer but receive no rewards
or admin notifications and are excluded from fulfillment views/actions, reminder
queries, and ordinary order/GMV metrics.

Funnel events use the existing `events` table. `cart_updated` contains only
`revision` and item count; `checkout_confirmed` contains only order ID, source,
and cart revision. Events have the authenticated internal `user_id`, and contain
no phone, address, raw customer text, or idempotency key. Test-account names are
prefixed with `test_`, including `test_order_created`, to keep them out of ordinary
event-name metrics. No-op writes and successful checkout retries emit no duplicate
cart/confirmation events.
