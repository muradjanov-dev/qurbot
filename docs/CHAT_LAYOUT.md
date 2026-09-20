# Chat layout — 2026-09-18

Historical release notes. Guest login and rollout behaviour below are superseded
by [Visitor/operator release](VISITOR_OPERATOR_RELEASE.md). Do not roll back to
the pre-guest images listed here after visitor accounts have been created.

The authenticated `/chat` is a standalone messenger screen matching the user's
reference: a light conversation canvas, one compact header with back arrow and
avatar, and a single composer row at the very bottom. The text field and send
arrow sit side by side. The storefront header, footer and bottom navigation
are not rendered on this screen. The three-dot menu contains operator handoff,
cart and account links. Guests keep the regular sign-in page layout.

Only the message history scrolls. The text field grows with multiline input,
up to a limit, and collapses after sending. Enter still adds a newline; the
arrow sends. Product cards and the shared cart remain available.

Previously, the history used up to 55dvh while the heading, a separate composer
card, footer and fixed navigation consumed additional height. At 390×700 the
composer ended at y=969 and the document was 1142px tall. The new flex layout
reserves the header/composer space and gives the remainder to history.
`visualViewport` and Telegram `viewportChanged` events update the available
height when the keyboard or Mini App viewport changes. Reading older messages
does not jump to the latest on polling.

The user's follow-up screenshot showed new markup with old styles. CSS and
JavaScript URLs now carry a content-derived version from `deps.ASSET_VERSION`:
updating any storefront asset changes the URLs so Telegram WebViews request
fresh files instead of reusing the previous unversioned assets.

## Verification

Run `make check` with the project's Python 3.12 development environment.
For the browser regression, install Playwright only in a local dev environment:

```sh
python -m pip install playwright
python -m playwright install chromium
python -m scripts.check_chat_layout
```

An existing Chromium executable can be selected with
`PLAYWRIGHT_CHROMIUM_EXECUTABLE`. Screenshots go to ignored `.artifacts/`.
The check renders the real templates and assets, intercepts all HTTP requests,
and covers three languages, 320–1280px widths, long history, multiline input,
sending, viewport resizing, simulated Telegram keyboard height and preserving
the reader's scroll position. It makes no production API or AI calls.
Physical Android/iOS keyboard behavior still needs a real-device check.

Local release checks passed: Ruff, formatting, mypy (160 source files),
JavaScript syntax, and `make check` (829 passed, 3 PostgreSQL-only tests skipped
without a local database). The browser regression passed all five viewport
cases and their resize/send checks. CI supplies PostgreSQL for the full suite.

## Deployment and handoff

Push `master` to `muradjanov-dev/qurbot`; `.github/workflows/deploy.yml` runs
CI, publishes the commit-tagged image, and deploys over SSH to Netcup. Verify
both `qurbot-web` and `qurbot-worker` image tags using `ssh netcup`, then check
`https://qur.standart-eko.uz/ready` and `/chat`. No schema migration is added.
The previous runtime image is
`5dc522935221d47def0d193b598448af051324ec`.

Rollback if required:

```sh
ssh netcup '/srv/stack/scripts/deploy.sh qurbot 5dc522935221d47def0d193b598448af051324ec'
```

After deployment, close and reopen the Telegram Mini App to load the new UI.
Project context: `docs/README.md`, `docs/SALES_RELEASE.md`,
`docs/WEBAPP_LOGIN_FIX.md`, and the workspace-level `../HANDOFF.md`.
