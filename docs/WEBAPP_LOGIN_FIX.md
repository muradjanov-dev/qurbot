# Telegram login correction — 2026-09-17

The reply keyboard used `KeyboardButton.web_app`, a launch mode without signed
`WebAppInitData`. The storefront expected signed `initData` to authenticate, so
even bot admins became anonymous web visitors. The login widget could then
render blank inside the Telegram WebView. This is an identity transport failure,
not justification to bypass signatures or grant a role from client input.

Source: [Telegram WebAppInitData](https://core.telegram.org/bots/webapps#webappinitdata).

The reply keyboard now sends a normal message, handled before AI text. It returns
an `InlineKeyboardButton.web_app` with signed launch identity. `/webapp` and
`/start webapp` give the same entry point. Startup also requests a native WebApp
menu; the inline entry remains independent of menu configuration.

Frontend authentication starts before cart initialization, preserves the launch
payload through same-tab navigation, displays errors, verifies that the session
cookie stuck, and follows the intended local destination without login loops.
The login page provides an explicit bot deep link even if the widget fails.
Raw initData is never put in URLs or logs. Existing database roles are retained.

Regression checks cover all three languages, inline launch type, signed admin
and customer login, forged/empty proofs, frontend missing data, cookie failure,
blocked storage, redirect safety and cross-page state. Earlier checkout smoke
tests began with an already-signed web session and therefore missed the Telegram
launch boundary. A real-device check still needs the user to close the old
Mini App, send `/webapp`, and press the new inline button.
