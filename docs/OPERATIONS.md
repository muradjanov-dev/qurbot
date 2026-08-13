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

## Admin web panel (SPEC §11)

Served from the same web service at `/admin`, behind HTTP Basic Auth
(`admin_basic_auth_user` / `admin_basic_auth_password` in config/env — set real
values before deploying; the defaults are placeholders).

Screens: `/admin/unmatched` (start here — highest-value queue), `/admin/aliases`,
`/admin/shops`, `/admin/offers`, `/admin/orders`, `/admin/dashboard` (daily metrics),
`/admin/llm-cost`.

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

`scripts/notify_deploy.py` runs as the last step of the web service's
`preDeployCommand` (after migrations). It DMs every `admin_tg_ids` entry via the bot.
This fires **before** the new version receives traffic (Railway's preDeployCommand is
pre-cutover, not post-start) — a deploy that fails health checks after this still
sends the notification. A failed Telegram send never fails the deploy (errors are
logged and swallowed).

## Rollback

1. In the Railway dashboard, redeploy the previous successful deployment for the web
   service (and worker, if it changed too) — this re-runs that version's
   `preDeployCommand`, so if the rollback also needs a DB migration downgrade, run
   `alembic downgrade -1` manually first (Railway doesn't infer downgrades).
2. If only the worker misbehaved (e.g. a bad cron job), you can roll back just the
   worker service independently — it shares no migration state with the web service.
3. Check `/admin/dashboard` and `/metrics` after rollback to confirm the funnel and
   error-relevant counters look normal again.
