# Guided cart and manual sales requests

## Customer and operator workflow

Bot cards include all three variants, even without a confirmed price. Presets
1/5/10 and deterministic custom quantity entry lead to an explicit add button.
The amount replaces the SKU's total quantity; a stale repeat never doubles it.
Cart, more products, edit quantity and return-to-variants actions remain visible.
Web product pages, chat cards and the shared cart follow the same quantity rules.
`/chat?cart=1` opens the guided cart directly, including from the legacy basket.

Unknown price/availability is never zero. A basket containing an unknown line,
or without a complete deliverable quote, goes to one manual request. Customers
confirm name, phone, district and address; saved contact details are prefilled.
`/sales-requests` shows their own request snapshots, status and resolution note.

The existing operator inbox shows contact/product cards. Only the conversation's
assigned admin can resolve an open request, with a mandatory note, as `agreed`
or `cancelled`. A conversation cannot return to AI while any request is open.
An enquiry is **not** an order, payment, warehouse task or revenue, even if agreed.
Handoff pauses AI and uses the existing admin notification outbox.

## Persistence and security

Migration `0021_sales_requests` adds `sales_requests`, `sales_request_items`, and
Telegram progress-message IDs/slots/leases on conversation jobs. Existing carts,
conversations, orders and prices are preserved. Application rollback must keep
the additive schema: schema downgrade deliberately refuses to delete enquiries.

Request creation locks conversation then cart. An owner-scoped idempotency key
and body fingerprint permit exact replay; revision rejects stale changes. The
immutable line/contact snapshot, handoff, event and cart clear commit together.
Subsequent products form the next basket. Test-account events are separately named.
API writes retain CSRF and authenticated ownership. Other customers cannot read
requests; another admin cannot resolve a conversation assigned to someone else.
Known-price checkout also rejects partial baskets instead of silently dropping
unknown lines. No seed/import values or stock quantities are invented.

## Waiting indicator

Seven localized messages rotate on 10-second phases, with a separate queued or
running label. After 60 seconds an honest delay message offers an operator.
Telegram edits one persisted message, while WebApp updates the existing request
indicator. Replies/errors/handoff end rotation. Status edits never gate the answer.
Initial Telegram send is reserved before sending: following an ambiguous network
failure, the indicator may be missing rather than sending a duplicate on retry.

## Verification and release

- Python 3.12, Ruff, mypy and full pytest, including real isolated PostgreSQL races.
- New integration tests cover mixed/unpriced requests, CSRF/ownership, idempotency,
  revision, clearing/new carts, operator claim/resolution, close guards, 155 entry,
  invalid quantities, back navigation, restart/status-edit failure and all texts.
- `scripts.check_sales_request_browser`: real staging catalog, mobile 155 entry,
  edit to 160 persisted in the request, drawer reopen, operator resolution and history.
- Existing chat/operator layout and checkout browser regressions remain applicable.
- `scripts.release_smoke`: synthetic guest/Telegram SQL+HTTP flows, ordinary order
  plus mixed enquiry/resolution, under an outer rollback. No paid AI or Telegram calls;
  no committed order, stock movement, request or sales metric.
- Full decoded pre-migration backup:
  `/srv/backups/postgres/qurbot-pre-guided-sales-20260921.dump`, 1,677,658 bytes,
  mode 0600. This is on-server backup, not off-site disaster recovery.
- Release via existing CI-gated commit-tagged image; verify web/worker SHA,
  readiness, migration head and rollback smoke after deployment.

No real test-bot token was supplied. Bot delivery is mocked; native Telegram phone
keyboard behaviour still needs a physical-device check. Browser layout tests
simulate Telegram viewport changes without changing the production webhook.
