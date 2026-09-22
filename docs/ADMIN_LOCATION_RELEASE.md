# Unified admin and optional delivery pin

The customer site and Telegram Mini App use the same responsive `/manage` panel.
Access requires a verified Telegram session and a current admin role. The bot's
super-admin list controls `/manage/admins`; a promoted admin cannot promote
another user. The old `/shop` and `/admin` roots lead to `/manage`. Existing
advanced admin routes accept the signed admin session, and their forms retain
same-origin write protection. HTTP Basic access remains available for legacy
automation and rollback.

The panel links the existing shop import, price, delivery, order and operator
screens with stats, users, aliases, unmatched queries, media review and cost
screens. `/manage/products` exposes the whole catalogue. Admins can create a
canonical product, optionally add a priced offer, edit its details and image,
and manage offers. Exact product identity uses a deterministic slug, so two
concurrent submissions cannot create the same variant. Similar existing rows
are shown before a new variant can be confirmed. Offer price writes append
price history. An offer's base unit cannot be changed while offers exist.

Orders, sales requests and saved addresses require a written address. The
optional pin can come from Telegram's LocationManager, browser geolocation or
a click on a Leaflet map. The user's typed text wins over a geocoder suggestion.
The three surfaces share `location.js`. A denied permission or geocoder failure
keeps the typed-address path available. Text-only saved addresses require a
district; nullable coordinates and sales-request pin columns are introduced by
`0022_optional_location`. Legacy rows keep their coordinates and old unpinned
sales requests remain readable. Pin-bearing sales requests carry the map point
through to the operator panel.

Leaflet 1.9.4 JavaScript, CSS and license are vendored under storefront static
assets. Map tiles default to OpenStreetMap with visible attribution. Set
`MAP_TILE_URL` and `MAP_TILE_ATTRIBUTION` to switch provider. The map opens on
demand; the application does not prefetch tiles.

Release gate: a verified pre-migration PostgreSQL backup is at
`/srv/backups/postgres/qurbot-before-admin-geo-20260922.dump` on Netcup.
Staging runs independently on `127.0.0.1:18081`; migration `0022` and a
synthetic admin/product, price history, typed address and pinned sales-request
smoke have passed there. Production should deploy only after CI and a fresh
staging image built from the final commit pass. After deployment, verify the
exact SHA on web and worker, `/ready`, `/manage` access control and the
customer address flow. Do not send real orders as a smoke test.
