# QurBot Operations Runbook

Phase 8 ops surface: scheduled jobs, admin web panel, `/metrics`, and Railway deploy.

## Migrations

Migrations run automatically on every deploy via the web service's `preDeployCommand`
(`railway.web.json`) — `alembic upgrade head` runs before the new version receives
traffic. To run manually (local dev or a one-off fix):

```
make migrate          # alembic upgrade head
alembic downgrade -1   # roll back one revision
```

The worker service does **not** run migrations — only the web service does, so a
deploy that touches both services doesn't race two `alembic upgrade head` runs
against each other.

## Scheduled jobs (`arq`, SPEC §10)

The worker process (`arq app.workers.main.WorkerSettings`) runs six cron jobs, defined
in `app/workers/schedules.py` and implemented in `app/workers/tasks.py`:

| Job | Schedule | What it does |
|---|---|---|
| `mark_price_staleness` | hourly | Escalates `shop_products.staleness_state`: `fresh → aging` after `price_staleness_aging_days` (default 5), `→ stale` after `price_staleness_stale_days` (default 7). |
| `nudge_shops` | daily 09:00 | DMs shop owners with aging offers, "Yangilash" button. |
| `recompute_trust_scores` | daily 03:00 | Rewrites `shops.trust_score` from freshness ratio, order accept rate, and rating. |
| `rollup_metrics` | daily 04:00 | Writes yesterday's funnel into `daily_metrics` (idempotent — safe to re-run for the same day). |
| `admin_digest` | daily 08:00 | DMs every `admin_tg_ids` entry a summary: unmatched queries, stale shop count, orders, GMV. |
| `abandon_baskets` | every 30 min | Baskets stuck in `awaiting_confirmation` for over `basket_abandon_hours` (default 24) become `abandoned`. |

Each job takes a Postgres advisory lock (`pg_try_advisory_xact_lock`, released
automatically on commit) so overlapping runs are safe no-ops, not double-processing.

**Manually trigger one job** (e.g. after a config change, to verify without waiting
for the schedule): run a single arq pass in burst mode, which executes any due cron
jobs once and exits —

```
arq app.workers.main.WorkerSettings --burst
```

To force a specific job to run regardless of schedule, call its `_*_impl` function
directly from a one-off script or a `python -c` snippet against a real DB session
(the same functions the tests in `tests/integration/test_worker_jobs.py` call).

**Inspect job health**: check worker logs (`worker_started`/`worker_stopped` on
boot/shutdown, `<job>_done` with counts on each successful run, `job_skipped_locked`
if a previous run is still holding the lock — that's expected under overlap, not an
error unless it persists across multiple scheduled ticks).

## Customer website (`/`)

Served from the same web service as the webhook. Set `WEB_ENABLED=false` to
take it down without touching the bot.

Before it can sign anyone in:

1. `TELEGRAM_LOGIN_BOT_USERNAME` = the bot's username, no `@`.
2. BotFather -> `/setdomain` -> the site's public domain. The Login Widget
   refuses to render for an unregistered domain, and this is the usual cause
   of "the login button does not appear".
3. `WEB_SESSION_SECRET` -- optional, but set it: without one the cookie key is
   derived from `BOT_TOKEN`, so rotating the token signs every customer out.

`WEB_DEV_LOGIN_ENABLED` must stay `false` in every deployment: it grants a
session for any Telegram id that is typed in.

Rate limits are per web process (`throttle_quote_limit_per_minute` for quoting
and PDF, `throttle_limit_per_minute` for parsing and geocoding). With several
replicas the effective limit multiplies -- move them to Redis if that becomes
a problem.

Orders placed on the site notify shops and admins through the same Telegram
messages the bot sends, and are marked `(sayt)` in the admin message.

## Admin web panel (SPEC §11)

Served from the same web service at `/admin`, behind HTTP Basic Auth
(`admin_basic_auth_user` / `admin_basic_auth_password` in config/env — set real
values before deploying; the defaults are placeholders).

Screens: `/admin/unmatched` (start here — highest-value queue), `/admin/aliases`,
`/admin/shops`, `/admin/offers`, `/admin/products` (full catalogue),
`/admin/listings` (photo review), `/admin/orders`, `/admin/dashboard`
(daily metrics), `/admin/llm-cost`.

### Full catalogue (`/admin/products`)

Every product, searchable and paged, **including ones hidden from customers**
by `enabled_category_slugs` — those are marked `yashirin`. Deliberately not
scoped by that allowlist: an operator who cannot see what they switched off has
no way to judge whether switching it off was right. The in-bot admin panel
lists the same thing with paging.

### The seeded demo market

The seed dataset creates 20 placeholder shops with roughly 4,000 offers whose
prices are `50000 * random(0.92..1.15)` regardless of product. Fine as dev
fixtures, wrong in production — customers were being quoted meaningless numbers,
and a real order was placed against one of those shops.

Migration `0010_retire_seeded_market` deactivates those shops and their offers.
It deactivates rather than deletes because `order_items.shop_product_id` is NOT
NULL, so deleting an offer already in an order would take the order history with
it — and because it has to be reversible. `alembic downgrade 0009_user_addresses`
puts the demo market straight back.

They do not come back on deploy: the pre-deploy seed runs with `--catalog-only`,
which stops before shops, offers and demo users, so catalogue changes roll out
without re-creating placeholder shops next to real ones.

### Photo review (`/admin/listings`)

Shop owners upload products with photos through the bot. Approving or rejecting
gates **only** whether customers see the owner's photos and description — the
price of a pending listing is live and competing in quotes from the moment it is
saved. Withholding a shop's prices because nobody has reviewed their photo yet
would punish them for uploading one.

Rejecting clears the photos and leaves the offer active, for the same reason: a
bad photo is not a reason to pull a real price out of the market.

Photos are served from `/admin/photo/{file_unique_id}`, reading our own stored
bytes rather than proxying Telegram — a `file_id` is scoped to the bot that
received it and cannot be rendered in an `<img>` tag at all.

## `/metrics` (Prometheus)

`GET /metrics` on the web service, no auth (matches typical Prometheus scrape
conventions — put it behind network-level access control at the infra layer, not
app-level auth, if the endpoint is reachable from outside your scrape network).

Exposes: `qurbot_quote_latency_seconds` (histogram), `qurbot_match_method_total`
(counter, by method), `qurbot_llm_cost_usd_total` (counter), `qurbot_stale_price_offers`
(gauge), `qurbot_db_pool_size` / `qurbot_db_pool_checked_out` (gauges).

Example Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: qurbot
    static_configs:
      - targets: ["<web-service-host>:8000"]
```

## Deploy notification

Fires from the web service's own startup (`app/main.py`'s lifespan, right after
`setWebhook`), gated on `register_webhook` so it only fires in real deployments,
not local dev. DMs every `admin_tg_ids` entry via the bot.

This was originally wired into Railway's `preDeployCommand` (pre-cutover, before
the new version receives traffic), matching `scripts/notify_deploy.py`'s
docstring intent — but that execution context turned out to have unreliable
outbound networking for the Telegram API call in practice (silent no-op, no
error in logs, despite the identical call working reliably from app startup).
Moved to startup instead: it now fires **after** traffic cutover, and on every
container start (health-check restarts, scale events) rather than strictly once
per genuine new deploy — a real tradeoff, accepted for reliability. A failed
Telegram send never blocks startup (errors are logged and swallowed).

`scripts/notify_deploy.py` still exists for ad-hoc manual notification but is no
longer wired into the deploy pipeline.

## Rollback

1. In the Railway dashboard, redeploy the previous successful deployment for the web
   service (and worker, if it changed too) — this re-runs that version's
   `preDeployCommand`, so if the rollback also needs a DB migration downgrade, run
   `alembic downgrade -1` manually first (Railway doesn't infer downgrades).
2. If only the worker misbehaved (e.g. a bad cron job), you can roll back just the
   worker service independently — it shares no migration state with the web service.
3. Check `/admin/dashboard` and `/metrics` after rollback to confirm the funnel and
   error-relevant counters look normal again.
