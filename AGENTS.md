# QurBot agent guide

QurBot is the Telegram and web sales assistant for construction materials.
Read the relevant section of `docs/SPEC.md` before editing a business rule.
`docs/OPERATIONS.md` contains domain behavior but has old Railway deployment
text; `.github/workflows/{ci,deploy}.yml` are the current deployment
source. Production uses the `master` branch, GitHub Actions and netcup.

## Working style

- Understand the request, repository guidance and relevant code before
  editing. Ask one focused question if a material product decision is
  unclear; otherwise state the assumption.
- Prefer the simplest change that meets the task; avoid unrelated
  refactors and dependencies.
- Keep edits within the requested behavior and preserve existing
  business, safety and release rules.
- Run relevant checks and report what changed, what passed, and
  anything that could not be verified.

## Where to look (task -> files)

- Catalog / price browsing: `app/bot/handlers/price_browse.py` (router
  `price_browse`); keyboards `app/bot/keyboards/inline.py`; data
  `app/db/repositories/catalog_repo.py` (`CatalogRepository`).
- Cart / customer checkout: `app/bot/handlers/customer.py` (router
  `customer`); cart rules in `app/services/cart_service.py` and
  `cart_policy.py`.
- Shop / seller portal: `app/bot/handlers/shop.py` (router `shop`) and
  `shop_listing.py` (router `shop_listing`, add-product wizard).
- Guided sales wizard (region/district/quantity):
  `app/bot/handlers/guided_sales.py` (router `guided_sales`).
- AI sales agent / LLM: `app/services/sales_agent.py` (`SalesAgent`) and
  `app/llm/` (`client.py`: `LLMClient`; `prompts.py`, `models.py`,
  `pricing.py`).
- Conversation orchestration (durable AI chat jobs):
  `app/services/conversation_service.py` (`ConversationService`,
  `DurableAgent`, `process_conversation`).
- User-facing text / translations: `app/core/i18n.py` (`MESSAGES` dict,
  `t()`), plus `chat_i18n.py` / `sales_i18n.py` for chat- and
  sales-specific strings. Never load these whole; see "Large files".
- Web storefront: `app/web/storefront/routers/` (`catalog.py`, `cart.py`,
  `checkout.py`, `basket.py`, `chat.py`, `manage.py` = seller dashboard)
  and `app/web/routers/` (JSON API: products, listings, aliases,
  offers, orders, dashboard).
- Workers / scheduled jobs: `app/workers/tasks.py` (arq tasks),
  `schedules.py`, `main.py`.
- Domain rules (pure logic, no I/O): `app/domain/pricing/`,
  `app/domain/matching/scorer.py`, `app/domain/parsing/` (`parser.py`,
  `excel_parser.py`), `app/domain/optimizer/solver.py`,
  `app/domain/normalize/text.py`.
- DB models / migrations: `app/db/models/` (e.g. `shop.py`);
  `app/db/repositories/` (one repo per aggregate); one Alembic revision
  per model change in `migrations/versions/`.
- Tests: `tests/unit/` mirrors app modules for pure-logic/formatter
  tests; `tests/integration/` exercises bot flows, web routes and DB
  repos via `tests/conftest.py` fixtures (Postgres). Add new tests next
  to the changed behavior.

## Large files -- do not read whole

Files over ~20 KB must not be opened in full. Find the symbol with
`rg -n <name> <file>`, then read only that range, e.g.
`sed -n '200,260p' file.py`. Biggest (approx.): `app/core/i18n.py`
121 KB, `app/bot/handlers/customer.py` 62 KB,
`app/services/conversation_service.py` 43 KB,
`app/bot/handlers/shop.py` 40 KB, `app/llm/client.py` 38 KB,
`app/services/sales_agent.py` 36 KB, `app/domain/optimizer/solver.py`
32 KB, `app/services/catalog_service.py` 28 KB,
`app/bot/keyboards/inline.py` 26 KB, `app/bot/handlers/shop_listing.py`,
`app/web/storefront/routers/manage.py`,
`app/db/repositories/catalog_repo.py`, `app/bot/handlers/common.py`
22-23 KB each, `app/bot/handlers/guided_sales.py` 20 KB. For `i18n.py`,
search the message key with `rg` and edit only the matching lines.

Never open unless the task is about them:
`tests/fixtures/catalog_snapshot.json` (190 KB) and other `tests/fixtures/*.json`;
static assets under `app/web/storefront/static/**` (images,
`leaflet.js`); `docs/eval_*.json`; `scripts/seed.py` (87 KB).

## Efficient workflow

- Start from the files named in the task ("relevant files", if given)
  instead of exploring from the repo root; prefer `rg` over opening
  files to locate a symbol, and open only the file(s) that need editing.
- Do not re-read a file already opened in this task unless it changed.
- Keep the diff minimal and scoped; add/adjust tests next to the
  changed code, in the matching `tests/unit/`/`tests/integration/` file.

## Where to work

- `app/domain/` is pure logic: Decimal money/quantity handling, no
  SQLAlchemy, aiogram or HTTP clients.
- `app/services/` coordinates business behavior; bot, website and
  worker paths use the same rules for the same action.
- `app/workers/` holds scheduled jobs: keep retries/duplicate execution
  safe; live orders/notifications are never smoke-test fixtures.

## Checks

- Human developers: run `make check` (ruff, mypy, pytest) before a PR.
  GitHub CI (`.github/workflows/ci.yml`) runs the same checks (`ruff
  check`, `ruff format --check`, `mypy app`, `pytest`) against
  PostgreSQL on every PR, pinned via `pyproject.toml`, and gates
  `deploy.yml` before `master`.
- On the Task Manager agent runner (no project deps installed): do NOT
  install deps or run `make check`/`pytest`. Make the smallest correct
  change, run only checks needing no install (e.g. `python -m
  py_compile <changed files>`, targeted `rg` checks), and state which
  checks were skipped and why. CI runs the full suite before merge.

## Delivery

- One task per branch and PR. State the behavior changed and the checks run.
- Database model changes need an Alembic migration in the same PR.
- Never run a second live bot using the production token. Use isolated staging
  or test credentials for Telegram behavior.
- Price, delivery, orders, authentication, mass messages, secrets, migrations
  and deployment settings need owner review. Do not auto-merge them.
- A coding task is complete only after its CI result and deployed commit are
  verified, including `/ready` for PostgreSQL and Redis.
