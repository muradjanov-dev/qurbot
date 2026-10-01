# Stock availability wording, fixed Tashkent delivery, and no ETA promises

Authority: user explicitly requests fixes and production deployment under the established no-PR workflow.

## Global constraints

- All child workers/reviewers gpt-6-luna/max, no nested agents; independent branches/disjoint file ownership, root integrates shared copy and verifies.
- Actual production SKU284 `Taxta 31x108x6000 mm` is active but has NO offer and NO reference price. All3374 offers have stock_qtyNULL; none has tracked stock. Do not fabricate price, change availability flags, mass-reactivate offers or bypass operator confirmation.
- NULL stock quantity is unbounded, not sold out. Missing/stale price is operator-confirmation state; explicit unavailable/archive rules still block automatic orders as before.
- Tashkent city delivery is50000UZS for any order value, including over5000000; no free-above threshold or minimum-order gate for that public policy. One logical active house shop QurBot/id25 currently has no delivery rules, so old fallback currently grants free delivery over5m.
- Keep generic/custom regional fees outside Tashkent and existing outside-service-area confirmation behavior. City is District.region `Toshkent`; `Toshkent viloyati` is a separate region. Missing/default public rule still uses50000 fallback but never value-based free delivery.
- Remove24–48-hour delivery promises from all user-facing bot/site/welcome/account/quote/AI copy; do not invent a replacement time. Internal ETA columns/optimizer ranking may remain for compatibility; no public time promise or old-policy AI knowledge.
- Existing placed orders, historical quote/receipt snapshots, currency/prices/cart quantities unchanged. New totals and pending confirmations must use current fee; existing bot/web recalculation and second confirmation must catch a saved old0 delivery total.
- No live Telegram test messages or second bot; fixtures isolated PostgreSQL/Redis. Quiet headless shell only (QURBOT_BROWSER_EXECUTABLE), never ordinary Mac Chrome.
- Direct master, no PR; reviewed/code-bearing commits through existing CI/deploy, verified backup before release and exact web/workerSHA + /ready after.

## Task 1: Stock/card availability diagnosis and fix

Own price_browse.py relevant detail/qty code, core/i18n.py ONLY product-card stock/no-offers messages, focused price-browse/unbounded-stock tests. Other workers do not edit i18n.py; root removes ETA messages after this task is integrated.

- Reproduce real callback card for active product with no offers/reference price: currently incorrectly says sold out. Return localized price/operator-confirmation copy and support path, retain selection/cart UX without fake zero price or complete automatic order.
- Verify NULL stock largevalid qty remains accepted; real out_of_stock/inactive/archived and needs-price-confirmation do not become automatically orderable. Distinguish statuses where existing data supports it, no migration/data modifications.
- Preserve price/photo/keyboard for actual live offers and all3languages. Inspect upstream price filtering for relevant defect; do not broaden legacy merchant/price data changes unrelated to screenshot.
- Red->green behavior tests via callback/actual DB; scoped lint/typecheck/tests, commit owned files and report proof. Shared i18n ETA untouched.

## Task 2: Fixed public delivery fee and administration

Own domain/optimizer/delivery.py, quote_service.py relevant tier mapping if needed, shop_repo.py delivery-rule persistence only, shop.py web delivery admin only, bot/handlers/shop.py delivery-rule admin only, shop_delivery.html, storefront checkout.py delivery_confirmed only, and associated delivery/optimizer/admin/checkout tests.

- Remove default5m-free calculation; default always50000,false,eligible. Ignore/remove free_above in public delivery path; generic base/custom regional fees and legitimate nonpublic min-order eligibility remain compatible where outsidecity applies.
- Tashkent public house calculation and saved/admin-entered defaults/district rules must reliably50000/free_aboveNULL/min_order0; stale or crafted old free-above/fee fields cannot re-enable discount. Prevent UI free-threshold/minorder controls from misleading current city policy. Outsidecity custom fee/address requirements stay.
- Missing house rule must still allow known Tashkent web delivery confirmation at50000 rather than requiring invented rule; outside area still requires existing explicit confirmation.
- Test below/exactly/above5m,6000000+50k grand total, legacy free rule, old web/bot saved0 quote must re-confirm before order; receipts replay and prior placed-order totals preserved. No needless migration: activehouse has no rows, source policy authoritative; if one is required justify/scopeddata only, coordinate root before choosing revision.
- Domain tests and real PG/web paths; no changes to shared i18n/salesAgent/bot customer.py/quoting.py owned Task3. Commit/report.

## Task 3: Remove delivery-time promises and update AI knowledge

Own bot/handlers/customer.py quote/ETA-render usages, bot/handlers/common.py ETA args/calls, web/storefront/quoting.py variant payload display, services/sales_agent.py prompt/get_knowledge/availability flags, services/pdf_service.py only ETA if found, relevant ETA/copy/AI policy tests. Do NOT edit core/i18n.py or fee/admin files owned others.

- Remove quote ETA line from bot and web visible payload/template; welcome/account no24–48 promise. Root surgically removes ETA strings/welcome lines in shared i18n.py AFTER Task1 commits; report exact required changes to root.
- AI system/tool knowledge explicitlycurrent Tashkent50000 regardlesssubtotal,nofree5m,no promiseddelivery time; remove ETA values from knowledge so old history doesn't become authority. Catalog-withoutprice needs operator confirmation, not sold-out claim; inspect availability output if necessary, coordinate Task1 contract.
- Keep internal optimizer ETA objects/serialized historical snapshots compatible. Three languages and bot/site/PDF summaries maintain correct totals and no empty raw key/extra promise line.
- Behavior tests exact no-time promise, get_knowledge feeevenwithoutDBrules and knownprice-state contract, relevant formatter/start/agent tests. Commit/report.

## Task 4: Root integration, shared copy, review and release

- Root i18n ETA edits after Task1: remove welcome ETA lines and quote_delivery_eta promise/calls, correct delivery admin copy if workers use keys. Update SPEC current public policy only, no unrelated rewrites.
- Fresh scoped reviews, then integration fullmakecheck actual isolatedPG/Redis/migration and headlessbrowser; confirm screenshots stockSKU unpriced behavior and6.383.060+50.000=6.433.060 newquote, no24–48 anywherepublic.
- Preserve confirmed orders/current historical totals; freshbackup, directmasterCIdeploy codebearingcommit, runtimeSHA/ready/migration/worker fee-sourcechecks. No production smokeorders/messages.
