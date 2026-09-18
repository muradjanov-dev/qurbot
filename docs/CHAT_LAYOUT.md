# Chat layout — 2026-09-18

The authenticated `/chat` now fills the available window. Only the message
history scrolls; the compact composer stays directly below it and above the
mobile navigation. The text field grows with multiline input, up to a limit,
and collapses after sending. Enter still adds a newline; the arrow sends.
The operator handoff button, product cards and shared cart remain available.
Guest visitors keep the regular sign-in page layout.

Previously, the history used up to 55dvh while the heading, a separate composer
card, footer and fixed navigation consumed additional height. At 390×700 the
composer ended at y=969 and the document was 1142px tall. The new flex layout
reserves the composer/navigation space and gives the remainder to history.
`visualViewport` and Telegram `viewportChanged` events update the available
height when the keyboard or Mini App viewport changes. Short windows use a
compact header. Reading older messages does not jump to the latest on polling.

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
`f82f4484a4e5af621585a6dc1e3306ba61b8d83b`.

Rollback if required:

```sh
ssh netcup '/srv/stack/scripts/deploy.sh qurbot f82f4484a4e5af621585a6dc1e3306ba61b8d83b'
```

After deployment, close and reopen the Telegram Mini App to load the new UI.
Project context: `docs/README.md`, `docs/SALES_RELEASE.md`,
`docs/WEBAPP_LOGIN_FIX.md`, and the workspace-level `../HANDOFF.md`.
