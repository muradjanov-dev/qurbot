# Visitor chat and operator inbox

## Customer experience

`/` opens the home page with catalogue sections and a separate AI chat link.
`/chat` opens the responsive messenger. No bot registration or login
is required. Signed Telegram initData is used when available; an unavailable
Telegram SDK does not block visitor access. A successful HTTP cookie roundtrip
is verified before reloading, so disabled cookies produce an error, not a loop.
The browser no longer stores Telegram credentials in sessionStorage.

Visitors have a real customer row with `tg_id=NULL`, an opaque HttpOnly cookie,
and a hashed, expiring server-side session (30 days). Existing Telegram sessions
continue to work. Cart/order/conversation ownership remains keyed to customer ID.
Phone is order contact information, never proof of account ownership. Cross-device
guest recovery/account merging and SMS verification are deliberately not added.

The cart opens inside chat. Quantity changes use cart revisions. Checkout collects
name, phone, district and address, then shows the live delivery-inclusive quote.
Only a separate confirmation places the order. Price changes require another
confirmation; retries reuse the same request until its outcome is known.
Missing delivery rules/pickup-only rules do not silently become free delivery.

## Operators

`/operator` requires a verified Telegram admin, including when a visitor cookie
already exists. Waiting, own and other assigned chats have separate paged filters.
Mobile home/catalogue/account headers expose a visible admin-only "Suhbatlar"
shortcut; the account page also has a prominent inbox link. Guest accounts have
an explicit administrator-login link in their cabinet; it does not grant access
or silently merge guest/customer identities. AI chat retains its admin menu link.
The inbox shows previews, timestamps and unread customer messages. Only the
claiming operator may reply or close; claiming remains transactional.

AI chats are excluded from the inbox and its transcript API. The customer confirms
handoff through the button; an AI suggestion alone cannot change mode. Operators
see previous AI context after handoff. Closing resumes AI on the next customer
message and removes the chat from the active inbox without deleting its history.

Telegram receives one queued notice per handoff event, not message copies.
Old claim/close callbacks and `/reply` guide admins to the page instead of editing
the conversation in the bot. Actual customer bot registration/checkout stays intact.
Customer operator notifications follow the last input channel; website and guest
conversations are read through polling, not copied to Telegram.

## Interfaces and safety

- `POST /api/session`: same-origin visitor bootstrap with `X-QurBot-Bootstrap: 1`.
- Existing chat/cart/order APIs accept a validated visitor session and retain CSRF.
- `GET /api/checkout/options`, `POST /api/checkout/preview`: live delivery quote.
- Orders accept `contact_name` and `district_id`; contact name is stored on the order.
- Operator list adds `scope`, `after_id`, `next_cursor`; read endpoint takes `sequence`.
- Shared Redis limits: 6 guest messages/minute, 30/day, 120/IP/hour;
  session creation 20/IP/hour and handoff 20/IP/hour. Redis failure fails closed
  for new visitor activity, never bypasses identity or escalates roles.
- Guest checkout limits are 5/customer/hour and 20/IP/hour, applied after live
  quote validation; already-created idempotent retries are exempt. Selected
  district and region are preserved in the order's delivery address.
- IP extraction peels trusted proxy hops from the right. Production's backend has
  no public port; default Docker proxy range is `172.16.0.0/12`. Override
  `TRUSTED_PROXY_NETWORKS` when changing the network topology.
- `GUEST_SESSIONS_ENABLED=false` stops new visitor creation without deleting
  existing customers/orders. Other guest limits are configuration fields.

Migration `0019_visitors_operator` preserves all existing rows and makes Telegram
ID optional, adds visitor sessions, operator read positions, input channel and
order contact names. `0020_test_customers` adds a private DB-only synthetic-account
marker so guest test orders cannot enter fulfillment or real sales metrics.
Never downgrade to an image that assumes every customer has a Telegram ID.
Schema downgrade intentionally refuses to erase guest-owned data.

## Removed and retained

Removed the superseded list form code, customer chat login
gate, stored Telegram-data retry loop and bot operator message-reply implementation.
The bot's onboarding, historical migrations, shop schema, import provenance,
catalogue management and legacy cart migration receipts remain in place.

## Verification and release

- Python 3.12 lint, formatting, mypy, full tests with isolated PostgreSQL.
- `scripts.check_chat_layout`: five viewport/language cases, keyboard and scrolling.
- `scripts.check_checkout_browser`: real browser, mocked API, contact/quote/repricing.
- `scripts.check_operator_layout`: long inbox/transcript wheel scrolling, retained
  reader position, Telegram keyboard and window resizing on mobile and desktop.
- `scripts.check_visitor_browser`: real isolated staging HTTP/worker, blocked Telegram
  SDK, visitor session, handoff, claim, reply, resume and mobile views.
- `scripts.release_smoke`: real PostgreSQL/ASGI checkout for Telegram and guest test
  customers. All fixtures/orders roll back; no Telegram/geocoder/paid AI calls.

Before production migration a full custom-format backup was created and decoded:
`/srv/backups/postgres/qurbot-pre-visitors-20260921.dump` (1,671,499 bytes, mode 0600).
It is an on-server backup, not a substitute for off-site disaster recovery.
Release uses commit-tagged images gated by CI. Check `/ready`, web/worker image SHAs,
both rollback smoke cases, and the public chat page after deploy. Physical-device
Telegram keyboard behaviour still requires a real-device check.
