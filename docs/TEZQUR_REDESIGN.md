# Tezqur storefront and currency pricing

The accepted design combines the compact admin workspace (prototype A) with
customer catalogue cards and category browsing (prototype B). Both use the same
light theme, green accent, Latin Tezqur wordmark and default Uzbek Cyrillic locale.
Existing language choices and Telegram sessions remain valid.

## Navigation

Customers browse catalogue → product → cart → checkout. AI is always reachable;
mobile navigation has Catalogue, AI, Cart, Orders and Account. Unverified visitors
see Telegram sign-in. Opening `/manage` as a guest goes through login; a verified
customer receives a readable permission message. Admin access still depends on
the authenticated Telegram identity and server-side role checks.

The admin sidebar has Overview, Products, Orders, Conversations, Customers and
Settings. Catalogue records and sellable offers are counted separately. Products
contain their packages, source prices and wholesale tiers. Settings contain the
exchange rate, delivery, administrator access and advanced operational tools.

## Price contract

The approved starting sales rate is **1 USD = 11 820.48 UZS**. It is an admin-managed
business setting, not a live market feed. `/manage/settings/currency` publishes a
new revision. The migration records its initial publisher as NULL; it does not
attribute that seed to a person.

`price_per_pack`, `price_per_base_unit` and the existing `currency=UZS` fields remain
canonical optimizer values. Offers and wholesale tiers also retain
`source_currency`, `source_price_per_pack`, `fx_rate_used` and `fx_rate_revision`.
Existing prices are backfilled as UZS without changing their amounts. No existing
UZS value is inferred to have originally been USD.

Decimal conversion happens on the server. Publishing a new rate and repricing
all USD-source offers and tiers happen in one transaction. Shared/exclusive
locking around the singleton rate protects quote reads from partially repriced
catalogues. FX-only repricing preserves stock, moderation and source-price
freshness. Confirmed orders keep their original immutable quote snapshots.

The customer sees UZS first, then USD. UZS-source prices show the dollar equivalent
with an approximation marker; USD-source prices show the original dollar amount.
Groups use spaces, meaningful UZS cents remain visible, and USD uses two decimal
places. Prices always identify their pack/unit. Settlement remains UZS.

Switching a price's currency requires a newly entered amount. Imports require an
explicit currency column or a selected file currency; ambiguous rows are shown
before application. Without a configured rate, UZS remains usable and USD writes
are rejected.

## Release validation

Run `make check` plus the PostgreSQL concurrency suite using
`SALES_TEST_DATABASE_URL`. The opt-in migration regression in
`tests/integration/test_telegram_cleanup_migration.py` upgrades 0025 to 0026 and
compares old offer/tier/history/quote/order columns exactly. Its reset operation is
restricted to the dedicated local migration-test database.

Use isolated staging for browser checks: all external Telegram notifications,
webhooks and AI providers stay disabled. Verify desktop/mobile layout, role menus,
three locales, login, CRUD and source-currency switching, live catalogue updates
without input loss, cart repricing and checkout confirmation. Remove throwaway
prototype runners, assets and variant selection from the production patch.

Pricing, auth and migration changes require owner review under `AGENTS.md`. Before
deployment, verify a fresh PostgreSQL backup. After deployment verify both web and
worker image commits, `/ready` database/Redis checks and the active migration.
