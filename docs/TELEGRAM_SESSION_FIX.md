# Telegram embedded-session regression

Production logs showed `/auth/webapp` returning 200 followed immediately by
`/api/cart` returning 401. The database account retained its admin role and was
not blocked. Chrome reproduced this with the old `SameSite=Lax` cookie in a
cross-site iframe; a top-level page worked.

HTTPS authentication and visitor cookies now use `HttpOnly; Secure;
SameSite=None; Partitioned`, with host-only scope. Plain HTTP development keeps
Lax cookies. Python 3.12 cannot serialize Partitioned through SimpleCookie, so
the helper appends that flag only to its own Set-Cookie field. Logout clears
both legacy unpartitioned cookies and the current partition. No database
migration or admin-role changes are required.

Server-side Telegram signature/freshness checks, account blocking, role checks,
and API CSRF tokens remain required. All storefront write routes also reject
cross-origin browser writes, including legacy HTML forms. Cookies never move
to JavaScript, localStorage, query strings, or a client-controlled admin flag.

`scripts.check_embedded_auth` runs real Chrome against the actual ASGI app and
an isolated SQLite database, with synthetic signed Telegram initData. Network
requests are intercepted; no real Telegram or paid AI calls occur. It checks:

- Old Lax policy reproduces the 200 -> 401 failure in an iframe.
- Admin login, authorized inbox access, reload and logout in a top-level page
  and cross-site frame with third-party cookies blocked.
- Guest sessions in both contexts, with operator access denied.
- Authentication cookies remain unavailable to JavaScript.

CI runs this browser regression using its preinstalled Google Chrome.
Integration tests separately cover forged signatures, customer/admin roles,
cross-site writes, missing CSRF, and HTTP/HTTPS cookie attributes.
`scripts.release_smoke` tests signed synthetic-admin authentication and logout
against the deployment database inside its existing outer rollback.

Physical Telegram clients with browser-specific storage restrictions still
need device confirmation; passing Chromium tests does not claim universal
WebView compatibility.

References: [Set-Cookie attributes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
and [partitioned cookies](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies/Partitioned_cookies).
