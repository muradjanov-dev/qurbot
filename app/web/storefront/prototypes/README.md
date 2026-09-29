# Tezqur design prototypes — throwaway

Question: which layout makes product/price management and customer ordering
clearest on desktop and in a phone-sized Telegram/browser window?

Run from the repository:

```sh
.venv/bin/python -m scripts.preview_redesign --port 18082
```

Open `http://127.0.0.1:18082/manage?variant=A`. The bottom bar switches between
A (trade counter), B (materials storefront), and C (split workspace), five
screens, and Uzbek Cyrillic/Latin/Russian. Left/right arrow keys switch variants
when a text field or dialog is not focused.

Existing page routes and their read paths are reused. The runner substitutes
an in-memory SQLite database populated from `scripts/seed.py` and a local demo
identity. The normal application cannot activate this preview from a URL:
rendering requires a non-production environment and the runner's application
state flag. The runner binds only to loopback and blocks all write HTTP methods.
Telegram, live model calls, webhook registration and external service credentials
are disabled/overridden before application imports.

Product names/images/prices come from the repository's catalogue data. The
exchange rate is the historical example in that seed, not a claim about today's
rate. USD/UZS editing, rate changes, cart and chat behavior are browser-memory
simulations; reload resets them. No production data is read or written by this
preview. Order/other secondary navigation links open a prototype information
message; the five evaluated screens are dashboard, products/editor, catalogue,
chat and cart.

Validation: 30 desktop/mobile screenshots; no horizontal page overflow or JS
errors; search in Latin/Cyrillic, product editing, price/source changes, cart
state across variant navigation, chat, three locales, and C's mobile drawers.
The HTTP write guard returns 405. Existing frontend/admin checks: 17 passed;
prototype Python lint/type checks pass. Full `make check`: 939 passed, 6
optional PostgreSQL/external checks skipped in this local prototype run.
QA images/logs are under `.artifacts`.

Decision: awaiting the user's separate admin/customer variant selections.
Suggested combination: A for admin, B for the customer storefront.

After selection, record the accepted visual decisions and implement them against
real services. Do not promote the mock JS to production. Remove losing variants,
the local renderer hook and the switcher before the production PR.
