# Tezqur admin workspace and browser sign-in

## Design decisions

The admin is an operational workspace: page actions, filters and records take
priority over decorative space. The changes use the search/filter/table/action
structure in [Shopify's resource-index pattern](https://shopify.dev/docs/api/app-home/latest/patterns/templates/resource-index),
the [Adobe Commerce grid controls](https://experienceleague.adobe.com/en/docs/commerce-admin/start/admin/tools/admin-grid-controls),
and [WooCommerce product management](https://woocommerce.com/document/managing-products/)
as references. No external UI framework or copied brand assets are added.

- Natural-height grid tracks prevent the dashboard and its cards stretching to
  the screen height. The main desktop gutter is 24px and sections use 16px gaps.
- Compact metrics retain readable type; the table has aligned numeric columns,
  clear statuses and a contained scroll area with sticky headers.
- Five recent real orders from the current house shop replace repetitive
  dashboard shortcuts. Empty data produces an honest empty state.
- Product thumbnails are buttons, with a visible eye on hover or keyboard focus
  and a persistent affordance on touch devices. The native dialog supports
  Escape, close button and backdrop close. Closing restores focus and both
  document and table scroll. Loading and failed-image states are explicit.
- Guest/account access is a prominent card; verified ordinary customers are not
  shown admin controls. Every new label supports Latin, Cyrillic and Russian.

## Telegram-confirmed browser sign-in

The flow uses Telegram's documented [private-chat deep links](https://core.telegram.org/bots/features#deep-linking):
the browser creates a five-minute challenge, the user opens the bot and presses
Start, then explicitly approves a matching code in the private chat. The original
browser completes sign-in and receives the normal signed session cookie. Admins
enter management by default; explicit safe return targets are retained.

The code is an intent check, not a credential. The Telegram link contains a
random public handle. A separate random secret stays in an HttpOnly browser
cookie; Redis stores its hash. Atomic scripts bind the challenge to one Telegram
sender, preserve its original expiry, and consume approval once. Approval alone
cannot authenticate a different browser. Current database role and blocked status
are checked before issuing a session; this flow never grants an admin role.

Telegram updates still arrive through the existing authenticated webhook. Only
the waiting browser checks its own challenge status; checks pause while hidden,
end on completion/expiry, and resume when the user returns. Redis failure closes
this flow safely; the existing widget and Mini App methods remain available.
Logout clears the pending challenge cookie as well as the normal session.

## Verification

`make check` remains the release gate. CI supplies isolated Redis so the Lua race,
expiry, binding and single-use tests always run. Local isolated browser checks:

- `python -m scripts.check_admin_workspace`: density, three languages, desktop
  and mobile, image-dialog keyboard/touch/error/focus/scroll behaviour.
- `python -m scripts.check_bot_login`: original-browser admin/customer sign-in,
  cross-browser rejection, replay, denial, cancellation, expiry, popup fallback,
  and server failure. It simulates only its own challenges inside an explicitly
  named staging container and never contacts Telegram.

Both scripts refuse non-loopback targets. No production order or login fixture
is created by these checks.
