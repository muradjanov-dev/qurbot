# QurBot

A Telegram bot that turns a free-text construction-materials shopping list into
priced quotes aggregated across partner shops in Tashkent, then places the order.
Full product/technical spec: [`SPEC.md`](SPEC.md). Operating a live deployment:
[`OPERATIONS.md`](OPERATIONS.md). Agent working rules: [`../CLAUDE.md`](../CLAUDE.md).

## Repo layout

```
app/
  api/          FastAPI routers: /health, /webhook, /metrics
  bot/          aiogram dispatcher, handlers, middlewares, keyboards, i18n strings
  core/         config, logging, i18n, exceptions, metrics
  db/           SQLAlchemy models + repositories (all DB access goes through these)
  domain/       pure logic: parsing, matching, pricing, optimizer, listing -- no I/O,
                no imports of sqlalchemy/aiogram/httpx (enforced by
                tests/unit/test_domain_purity.py)
  llm/          Stage 3 disambiguation + whole-message parse fallback
  services/     orchestration layer: wires domain + repositories + llm
  web/          admin panel (FastAPI + Jinja2, HTTP Basic Auth)
  web/storefront/  the customer website: same product as the bot, Telegram sign-in
  workers/      arq background jobs + cron schedule
migrations/     Alembic revisions
scripts/        seed.py, load_test.py, backup.py, restore.py, notify_deploy.py
tests/          unit/ (no DB), integration/ (sqlite in-memory via test_session fixture)
```

## Shop product uploads

A shop owner adds a product in one action: send photos with a caption like
`Sement M400 50kg qop 52000 so'm`. Whatever the caption doesn't say is asked
for, and nothing else.

Two invariants hold this together:

- **Nothing is lost.** Every answer is written to `shop_product_drafts` before
  the next question is asked, and photo bytes are stored in
  `product_photo_blobs` on receipt. A redeploy, a Redis eviction or a user who
  walks away for two days costs at most the question in flight — the draft is
  found again by owner id and resumes where it stopped. A Telegram `file_id` is
  treated as a cache, never the store of record: it dies with the bot token.
- **A price is never saved on a guess.** A caption marking the price
  (`52000 so'm`, `narx 52000`, `= 52000`) is trusted. A bare trailing number is
  shown back for one-tap confirmation first. Price feeds `price_per_base_unit`,
  which decides every quote the shop appears in, so it does not get to be
  implicit. See `app/domain/listing/quick_entry.py`.

Customers never see which shop supplied a line — quote cards, the PDF and order
summaries present one merged basket. Shop attribution stays on `order_shop_parts`
and the shop notifications, where fulfilment actually needs it.

Stock is respected when quoting: a shop that can't cover the requested quantity
is not offered, and if nobody can, the shop holding the most is offered rather
than showing the customer nothing (`BasketOptimizer._filter_by_stock`).

## The customer website

`app/web/storefront/` serves the site at `/` from the same web service as the
bot webhook and the admin panel. It is not a second product: a visitor signs in
with Telegram and lands on the very `users` row the bot writes, so orders,
saved addresses and pebbles are shared between the two.

What it covers: paste-a-list parsing, the catalogue, the basket, the optimised
quote cards (white-labelled exactly as the bot's are), checkout with saved
addresses, order history, the cabinet, and a shop-owner portal (prices, stock,
delivery terms, orders, Excel import).

Two ways in, both proved offline against the bot token, neither needing a
second password:

- **Login Widget** for a browser tab. Requires `TELEGRAM_LOGIN_BOT_USERNAME`
  *and* the site's domain registered on the bot (BotFather -> `/setdomain`).
  Without both, the widget cannot render and the site says so.
- **Mini App** when the site is opened inside Telegram: `initData` is posted to
  `/auth/webapp` and verified with the Mini App key derivation.

The session is a signed cookie (`qb_session`), keyed from `WEB_SESSION_SECRET`
or, unset, derived from `BOT_TOKEN` -- rotating the token signs everyone out
unless the secret is set explicitly.

`WEB_DEV_LOGIN_ENABLED=true` adds a local sign-in form that takes any Telegram
id. It is gated on its own setting, never on `APP_ENV` (which defaults to
`local`), so it cannot be left on by forgetting to set the environment.

Browsing, the basket and a quote need no account; placing an order does. The
basket lives in the browser's `localStorage`; the server never trusts a price
from it and recomputes the quote before writing an order, refusing the order if
the total moved (the customer is shown the new one and asked again).

## Launch catalogue scope

Only the categories in `settings.enabled_category_slugs` are offered to
customers, and only their products can be matched. Quoting something we cannot
actually source is worse than saying we do not carry it, so the restriction
applies to the matcher as well as to browsing.

At launch that is: boards (fanera/MDF/DSP), fasteners, drywall + profiles, and
timber. Widening the range is a config change -- set the list to `[]` to switch
the full catalogue back on. No data is deleted by narrowing it.

## Delivery addresses

Customers save places as **map pins, not typed text**. A Tashkent street
address often does not resolve to a findable location, so the pin is what the
courier navigates to and the text is a label the customer confirmed on top of
it.

Signup is two steps -- language, then a location -- because the district is
derived from the pin rather than asked for, and the phone is collected at
checkout where it is actually used. Declining to share a location falls back to
picking a district by hand, so it is never a dead end.

Reverse geocoding uses Yandex when `YANDEX_GEOCODER_API_KEY` is set (much
better Uzbek street coverage) and keyless Nominatim otherwise. Deliberately not
the LLM: a language model does not know what stands at a coordinate and will
produce a fluent, confident, wrong street. Whatever the geocoder returns is
shown to the customer to confirm or correct before it is saved, and a geocoder
outage degrades to "type your address" rather than blocking the order.

Customers keep several addresses and pick one at checkout, which is the point:
the right address depends on which site the delivery is going to today.

## Local setup

Requires Docker (for Postgres + Redis) and Python 3.12.

```bash
cp .env.example .env        # fill in BOT_TOKEN at minimum for the bot to do anything real
make install                # pip install -e ".[dev]"
docker compose up -d postgres redis
make migrate                # alembic upgrade head
make seed                   # populates a realistic dev dataset (deterministic, fixed seed)
make run                    # uvicorn, reload on
make worker                 # in a second terminal: arq app.workers.main.WorkerSettings
```

`REGISTER_WEBHOOK=false` (the `.env.example` default reversed for pure local dev,
see comments there) lets `/health` and a synthetic POST to the webhook route work
without a public URL or a real bot token.

## Tests

```bash
make check     # ruff check + ruff format --check + mypy app + pytest
```

Full suite takes several minutes (the LLM-fallback held-out evaluation and the
worker-job integration tests are the slow ones). `tests/unit/` alone (no DB) is
fast and safe to run on every save.

## Deploying

Railway config lives at repo root: `railway.json` (web service) and
`railway.worker.json` (worker service — the CLI has no way to set a per-service
config-as-code path, so deploying the worker means temporarily swapping which
file is named `railway.json`, or setting the worker service's Config-as-code
Path to `railway.worker.json` once in the dashboard). See `OPERATIONS.md` for
the full runbook, scheduled jobs, admin panel access, and rollback steps.

Two things Railway needs that aren't obvious from the config files alone:
- A `PORT` env var matching the container's listen port — `railway domain --port`
  alone does not reliably bind the domain's target port before a first successful
  deployment exists.
- `healthcheckTimeout` needs enough headroom for cold start (image pull + Python
  imports + the Telegram `setWebhook` call) — 30s was too tight in practice; 60s+
  is safer.

## Load testing

```bash
python -m scripts.load_test   # 50 concurrent baskets end-to-end, asserts p95 < 2s
```

## Backup / restore

```bash
python -m scripts.backup [output_dir]           # pg_dump to a timestamped file
python -m scripts.restore <dump_file> --yes      # DESTRUCTIVE, pg_restore --clean
```

Both shell out to `pg_dump`/`pg_restore`, so those need to be on PATH (same major
version as the target Postgres).
