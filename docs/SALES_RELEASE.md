# Interactive sales release

Approved scope: one QurBot seller; add-only Excel import; durable shared bot/web
cart; durable chat; product cards; existing-admin handoff; catalogue/rules
retrieval; real AI evaluation reservations capped at USD 5.

## Baseline

- Production inspected 2026-09-17: `2b18f24`, schema `0016_order_delivery_pin`.
- Web healthy, worker running; VPS 8 GB RAM with ~5.8 GB available.
- `/srv/backups/postgres` was empty at inspection. Create and validate a fresh
  backup before production migrations/import; do not infer backup coverage.
- Local Python 3.12 environment: `.venv312` (ignored).
- Baseline Python 3.12 suite: 744 passed in 56.18 seconds (4 workers).
- Fresh backup: `/srv/backups/postgres/qurbot-before-sales-20260917.dump`,
  1,610,784 bytes, mode 0600; both archive listing and full `pg_restore`
  decoding to `/dev/null` passed. This is an on-server backup, not off-site DR.

## Gates

1. Baseline lint/types/tests; isolated staging DB, Redis and dummy bot token.
2. Add-only import dry run and repeat-import test; keep ambiguous prices and
   unknown stock unorderable. Never overwrite existing offers.
3. Shared cart, checkout concurrency/idempotency and cross-channel validation.
4. Chat, request deduplication, restart recovery and operator isolation.
5. Full checks, staging PostgreSQL migrations and smoke, CI, SHA deployment.
6. Production readiness and test-account functional smoke. No customer data
   copied to staging; no test orders dispatched to fulfilment.

## Operational defaults

Staging must not receive production BOT_TOKEN or register its webhook. Until a
separate test bot token is supplied, bot tests use mocked Telegram transport.
No real AI tests run without a persisted reservation ledger capped at USD 5.
Production deployment status is recorded only after inspecting the running SHA.

## Progress

- Implementation, local/staging checks and production rollout completed.
- VPS staging Postgres 18 and Redis 7 run on a separate Compose network, with
  a dedicated volume; no production customer data has been copied.
- Production comparison is read-only; matching uses explicit source identities
  and exact variant attributes, with ambiguous identities held for review.
- Final production dry-run identifies 20 new timber variants. All 20 were
  imported on staging; a second apply added zero rows. Existing prices/offers
  remain untouched. 18 additions are price-on-request; all have unverified
  stock and no automatically created offer.
- 57 source rows are held: 1 heading, 41 ranges/lists, 5 uncertain sheet
  dimensions, 8 ambiguous stud identities, 2 Agraf variant/unit layouts.
  These are not guessed into individual SKUs. No price-only row is held.
- Real PostgreSQL races pass: stale cart revision, two-admin claim, and
  double checkout. Final complete suite with PostgreSQL: **814 passed in 56.03s**;
  Ruff/format/mypy, JavaScript syntax and git whitespace checks pass.
- Staging HTTP/worker chat smoke passes request deduplication, model-off
  fallback, handoff, claim conflict, user ownership, operator reply and AI resume.
- Staging `/chat` returns HTTP 200; functional order smoke passes and verifies
  rollback. Baseline and new additive migrations were exercised on PostgreSQL18.

## Production verification — 2026-09-17

- Runtime commit: `f091c131f7a24cc3ae3a8c8d21b13b6364b1b120`, verified on both
  production web and worker image tags. Web healthy, worker running; schema head
  `0018_conversations`.
- [GitHub CI/build/deploy run](https://github.com/muradjanov-dev/qurbot/actions/runs/35242188844)
  completed successfully. Measured job times: build 50s, CI 189s, deploy 34s;
  build and CI run in parallel. Existing pip/GHA Docker caches retained; local
  Docker builds additionally cache pip downloads.
- [Production chat](https://qur.standart-eko.uz/chat) returns 200. `/ready`
  verifies both PostgreSQL and Redis. Full rollback-only HTTP checkout smoke
  passed before and after import, including repricing and repeated confirmation.
- Fresh pre-release backup:
  `/srv/backups/postgres/qurbot-pre-sales-release-20260917.dump`, 1,610,784 bytes,
  mode 0600; full archive decoding passed before deploy.
- Production import committed **20** new timber variants; second transactional
  apply created **0**. All 20 have unverified stock, 18 are price-on-request,
  and **0** live sale offers were invented. Existing offer price/stock count and
  content hash match the pre-release snapshot.
- A newly imported public product page returns 200 and does not expose an
  automatic add-to-cart control.
- Source review is still required for 57 held rows described above. A separate
  staging Telegram bot token is still required for real-device test-bot checks;
  mocked bot tests, staging HTTP/worker checks and live three-language model
  tests are complete. No production customer records were copied to staging.

The runtime SHA above is intentionally immutable. Subsequent documentation-only
commits do not imply a different deployed application image.

## Repeatable staging and functional check

`docker compose -p qurbot-staging -f compose.staging.yml up -d --build`
starts the isolated stack, bound only to `127.0.0.1:18081`. For a released
image set `STAGING_IMAGE=ghcr.io/muradjanov-dev/qurbot:<full-sha>` and use
`up -d --no-build`. Do not supply production environment files.

`docker compose -p qurbot-staging -f compose.staging.yml exec -T web python -m scripts.release_smoke`
checks product → shared cart → live quote → changed-price reconfirmation →
order → idempotent repeat → cart clear. It uses a synthetic test identity and
an outer PostgreSQL transaction with savepoints, then verifies rollback.
No Telegram transport, paid AI, or fulfillment notification is started.
PostgreSQL sequence counters may advance; no test business rows are retained.

## Live AI evaluation

`scripts.eval_sales_chat` refuses production, requires a persistent reservation
ledger, accepts the key on stdin only, and exposes read-only tools. Three prompts
exercise Uzbek Latin, Uzbek Cyrillic and Russian catalogue queries. SDK retries
and provider-side model fallback are disabled for these tests. Each attempt
reserves full serialized input bytes plus framing, the maximum output, and
cache-write pricing; failed calls retain their reservations.

Claude Opus 5 standard pricing was rechecked on 2026-09-17 against
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing):
$5 input / $25 output per million tokens; 5-minute cache writes $6.25.
The dedicated staging `stage_eval` volume retains the ledger across deploys.
Do not delete/reset it between test attempts.

2026-09-17 live evaluation: all three languages returned catalogue-backed
answers and called `search_products` plus `get_knowledge`. Usage-derived cost
estimate: **$0.058036**; pessimistically reserved cumulative ceiling: **$0.545164**
of **$5**. Ledger: `/eval-budget/sales-release-20260917.json` in the staging web
container's persistent `stage_eval` volume. The secret was streamed privately
from the production configuration into the isolated one-shot evaluation process,
not stored in staging configuration; production customer data was not copied.
