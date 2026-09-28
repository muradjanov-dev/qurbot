# Admin catalogue and customer conversation update

The storefront admin panel supports catalogue creation, editing, archival and
restoration, including local photos and offer pack/unit/price changes. Product
and offer form writes use the signed session's CSRF token. Archival retains
historical references and offer activation state; every active-offer query also
requires an active canonical product.

Offer stock quantities are no longer tracked. Migration `0024_unlimited_stock`
clears existing values; all runtime offer writers store NULL. Explicit stock
status, product activation, fresh pricing, valid units and numeric quantity
limits continue to gate quoting. The old numeric values cannot be reconstructed
by downgrading this migration; take a database backup before the production
upgrade.

Customer catalogue/product pages request an HTML fragment every five seconds
while visible. The owner explicitly approved this browser refresh behavior in
the implementation plan. Telegram remains webhook-driven. Product quantity and
purchase controls survive fragment replacement; image URLs identify the current
photo and media responses revalidate caches. An archived open card becomes
unavailable. Open cart drawers refresh current line prices and invalidate a
previous checkout preview when pricing changes, without replacing contact or
address inputs or replaying an uncertain order request.

Each AI turn starts from the current durable cart. Read-only answers survive a
concurrent cart revision; a conflicting stateful operation returns a separate
cart-conflict response without reapplying old quantities. Basket mutations clear
old search cards. A delivered reply removes the temporary progress message;
terminal errors do not announce success. The delivery notice is localized as
“Toshkent bo‘ylab yetkazib berish — 50 000 so‘m.” Existing numeric delivery
fees and free-delivery thresholds are unchanged.

Migration `0025_telegram_cleanup` adds a durable registry for explicitly selected
customer AI/guided messages. Known inbound messages, AI replies, status messages
and variant/cart messages expire 24 hours after sending. The five-minute worker
uses bounded batches and leases, retries temporary failures and retires messages
that Telegram no longer allows deleting after 48 hours. It never deletes
conversation history, carts or orders. Order/checkout confirmations, receipts,
order-status messages, and admin chats are excluded. Existing unregistered
Telegram message IDs are never guessed. A customer promoted to admin after
registration is protected again when deletion is attempted.

## Verification

- `make check` with an isolated PostgreSQL database, including row-lock races.
- `python -m scripts.check_embedded_auth` for Telegram iframe session behavior.
- Isolated `compose.staging.yml` web/worker; `/ready` must confirm PostgreSQL and
  Redis. Telegram notifications, live model calls and webhook registration are
  disabled in this environment.
- `python -m scripts.check_catalog_live --category-id 17` exercises two browser
  contexts: admin edits, live name/price/photo, retained quantity/contact fields,
  checkout invalidation, archive and restore. Its target is restricted to
  loopback. Seed synthetic users 499990001 (admin) and 499990002 (customer) plus
  explicit staging delivery rules before running it; the script never orders.

## Production rollout

Owner review is required for authentication, pricing-related behavior and
migrations. Merge only after review and green CI. Take and validate a PostgreSQL
backup before release; master CI/build/SSH deployment updates both web and worker.
Verify their image tags match the approved commit, `/ready` returns 200 and both
dependency checks pass. Monitor cart-conflict/outage events and cleanup worker
errors. A code rollback retains compatible added schema; restore backed-up stock
quantities only if rolling back to quantity tracking.
