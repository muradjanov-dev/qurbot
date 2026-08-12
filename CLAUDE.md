# CLAUDE.md — QurBot

## Read first
- `docs/SPEC.md` is the source of truth. If my request contradicts it, say so and ask.
- Work in the phase order from SPEC §15. Do not skip ahead. Do not build Phase 4 code
  while Phase 2 tests are red.

## Workflow per task
1. State a short plan (files you'll touch, why) before writing code. Wait if the task is
   ambiguous — ask one specific question rather than guessing.
2. Write the test first for anything in `app/domain/`.
3. Implement.
4. Run `make check` (ruff + mypy + pytest). Do not report done while it fails.
5. Give a 3-line summary: what changed, what's verified, what's next.

## Code rules
- `app/domain/` is pure: no `import sqlalchemy`, no `import aiogram`, no `httpx`, no
  `datetime.now()` (inject a clock). Enforced by an import-linter test.
- `Decimal` for all money and quantities. `float` for money is a bug.
- All I/O is async. No blocking calls in handlers — `openpyxl`/`pandas` work goes to a
  thread via `asyncio.to_thread` or to the arq worker.
- Type hints everywhere. `mypy --strict` passes on `app/domain/` and `app/services/`.
- No magic numbers. Thresholds, weights, limits, timeouts → `core/config.py`.
- No bare `except:`. Raise typed domain exceptions from `core/exceptions.py`.
- Repositories return domain objects or explicit row tuples — never leak lazy-loaded ORM
  objects past the service layer.
- Every user-facing string goes through i18n with `uz_latn`, `uz_cyrl`, `ru` variants.
- Migrations: every model change gets an Alembic revision in the same commit.

## Don'ts
- Don't invent product data, shop names, or prices outside `scripts/seed.py`.
- Don't add a dependency without telling me what it replaces and why.
- Don't use polling in production code paths; webhook only.
- Don't call the LLM in a loop over basket lines. Batch, or don't call it.
- Don't write files outside the repo. Don't commit `.env`.
- Don't silently widen a threshold to make a test pass.

## Commits
Conventional commits, one logical change each: `feat(optimizer): add local search pass`.
Commit at the end of every phase with the test suite green.
