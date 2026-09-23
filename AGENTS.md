# QurBot agent guide

QurBot is the Telegram and web sales assistant for construction materials.
Read `CLAUDE.md` and the relevant section of `docs/SPEC.md` before editing a
business rule. `docs/OPERATIONS.md` contains domain behavior but has old Railway
deployment text; `.github/workflows/{ci,deploy}.yml` are the current deployment
source. Production uses the `master` branch, GitHub Actions and netcup.

## Where to work

- `app/domain/` is pure logic. Preserve Decimal money and quantity handling;
  do not import SQLAlchemy, aiogram or HTTP clients there.
- `app/services/` coordinates business behavior. Bot, website and worker paths
  should use the same underlying rules when they represent the same action.
- `app/workers/` contains scheduled jobs. Keep retries and duplicate execution
  safe; live customer orders and notifications are never smoke-test fixtures.
- `tests/` has unit and integration checks. Run `make check` (ruff, mypy, pytest)
  before opening a PR. CI runs the same checks with a PostgreSQL test service.

## Delivery

- One task per branch and PR. State the behavior changed and the checks run.
- Database model changes need an Alembic migration in the same PR.
- Never run a second live bot using the production token. Use isolated staging
  or test credentials for Telegram behavior.
- Price, delivery, orders, authentication, mass messages, secrets, migrations
  and deployment settings need owner review. Do not auto-merge them.
- A coding task is complete only after its CI result and deployed commit are
  verified, including `/ready` for PostgreSQL and Redis.
