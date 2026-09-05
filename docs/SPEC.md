# PROJECT SPEC — "QurBot": Construction Materials Price Aggregator (Telegram Bot)

> **How to use this file:** Save it as `docs/SPEC.md` in an empty repo, and save the
> "Agent Operating Rules" section (§14) as `CLAUDE.md` at the repo root. Then start
> Claude Code and give it the Phase 0 prompt from §15. Do **not** ask the agent to
> build everything in one shot — go phase by phase.

---

## 1. Product summary

A Telegram bot where a customer pastes a free-text list of construction materials with
quantities. The system parses it, matches each line to a canonical SKU, looks up live
offers across many partner shops, and returns **3–5 optimized basket variants**
(cheapest / fastest / single-shop / premium / balanced). The customer picks one, an order
is created, and the relevant shops are notified.

Second side of the marketplace: partner shops update their prices through a supplier bot
(Excel upload or one-line text) or a web form.

**Primary market:** Uzbekistan. Users write in Uzbek Latin, Uzbek Cyrillic, and Russian —
often mixed in the same message. The system must handle all three.

**Non-goals for v1:** in-bot payments, driver/logistics tracking, multi-city expansion,
mobile app.

---

## 2. Hard technical constraints

| Concern | Decision |
|---|---|
| Language | Python 3.12 |
| Bot framework | aiogram 3.15+ (webhook mode, not polling, in prod) |
| Web layer | FastAPI (webhook receiver + supplier API + admin API + `/health`) |
| DB | PostgreSQL 16 with `pg_trgm`, `unaccent`, `btree_gin` extensions |
| ORM | SQLAlchemy 2.0 async + `asyncpg`. No sync engine anywhere. |
| Migrations | Alembic. Every schema change gets a migration — never `create_all` in prod. |
| Cache / FSM | Redis (aiogram `RedisStorage`, plus app-level cache) |
| Background jobs | `arq` (Redis-backed) — separate worker process |
| LLM | OpenAI-compatible Chat Completions API (`gpt-5.6-terra`), used **only as fallback**, see §6 |
| Config | `pydantic-settings`, all secrets from env, `.env.example` committed |
| Logging | `structlog`, JSON output, request/update correlation IDs |
| Tests | `pytest` + `pytest-asyncio` + `testcontainers` (or a dedicated test DB) |
| Lint/format/types | `ruff` (lint + format) + `mypy --strict` on `app/domain/` |
| Deploy | Docker + `docker-compose.yml` for local; Railway for prod (web + worker services) |

Everything must run locally with a single `docker compose up`.

---

## 3. Architecture rules (non-negotiable)

```
app/
  main.py                   # FastAPI app factory, lifespan, router mounting
  core/
    config.py               # Settings (pydantic-settings)
    logging.py
    exceptions.py           # domain exception hierarchy
    i18n.py                 # uz_latn / uz_cyrl / ru string catalogs
  db/
    base.py                 # DeclarativeBase, mixins (TimestampMixin, SoftDelete)
    session.py              # async engine + sessionmaker + get_session dep
    models/                 # one file per aggregate
    repositories/           # data access only, returns domain objects or ORM rows
  domain/                   # ⚠️ PURE. No DB, no network, no aiogram imports.
    normalize/              # text + unit normalization, transliteration
    parsing/                # free-text basket -> ParsedLine[]
    matching/                # candidate scoring, alias resolution logic
    optimizer/               # basket optimization algorithms
    pricing/                 # unit-price math, delivery cost math
    models.py                # frozen dataclasses / pydantic models for domain types
  services/                  # orchestration: DB + domain + LLM + notifications
    basket_service.py
    quote_service.py
    order_service.py
    catalog_service.py
    supplier_service.py
  llm/
    client.py               # LLM API wrapper: retries, timeout, token budget
    prompts/                # versioned prompt templates as .txt/.j2 files
    cache.py                # hash(input) -> result cache in Redis + Postgres
  bot/
    dispatcher.py
    middlewares/            # throttle, i18n, user_ctx, db_session, error
    handlers/                # start, basket, quote, order, supplier, admin
    keyboards/
    states.py                # FSM state groups
    formatters/               # domain result -> Telegram message text
  api/
    routers/                 # webhook, supplier, admin, health
  workers/
    tasks.py                 # arq task definitions
    schedules.py              # cron: staleness check, digests, metrics rollup
migrations/
tests/
  unit/                      # domain/ tests — must run in <5s, no DB
  integration/                # repositories + services, real Postgres
  e2e/                        # simulated Telegram updates through the dispatcher
```

**The rule that matters most:** `app/domain/` is pure. Parsing, matching scoring, and
basket optimization are deterministic functions over plain data structures. This is what
makes the project testable and fast to iterate. If a function in `domain/` needs data,
the caller passes it in.

---

## 4. Data model

Generate Alembic migrations for all of this. Use `BIGINT` PKs, `TIMESTAMPTZ` everywhere,
and add the listed indexes explicitly.

### 4.1 Reference / catalog

**`units`** — `code` (pk, e.g. `kg`, `dona`, `m2`, `m3`, `litr`, `qop`, `quti`, `rulon`),
`name_uz`, `name_ru`, `dimension` (`mass|count|area|volume|length`), `base_code`,
`factor_to_base` (numeric).

**`categories`** — id, `parent_id` (self-fk), `slug`, `name_uz`, `name_ru`, `sort_order`,
`icon`. Tree, max depth 3. Seed: Sement va qorishmalar, G'isht va bloklar, Metall va
armatura, Yog'och, Bo'yoq va lak, Plitka, Santexnika, Elektr, Izolyatsiya, Gipsokarton,
Tom yopish, Asboblar, Qurilish aksessuarlari.

**`canonical_products`** (the SKU table) —
`id`, `slug` (unique), `name_uz`, `name_uz_cyrl`, `name_ru`, `brand`, `category_id`,
`base_unit_code` (fk units), `attributes` (JSONB — e.g. `{"grade":"M400","size":"30x30","thickness_mm":8}`),
`tier` (`economy|standard|premium`), `is_active`, `search_doc` (generated tsvector /
normalized text column for trgm).
Indexes: `GIN(search_doc gin_trgm_ops)`, `btree(category_id)`, `GIN(attributes jsonb_path_ops)`.

**`product_aliases`** — `id`, `canonical_id` (fk), `alias_norm` (normalized text, unique
with canonical_id), `alias_raw`, `source` (`seed|shop|llm|admin|user`), `confidence`
(0–1), `hit_count`, `last_hit_at`, `is_approved`.
Index: `unique(alias_norm)` where `is_approved` — this is the hot path, must be an exact
hash/btree hit.

### 4.2 Supply side

**`districts`** — `id`, `region`, `name_uz`, `name_ru`, `centroid_lat`, `centroid_lng`.
Seed Tashkent city districts + Tashkent region first.

**`shops`** — `id`, `name`, `legal_name`, `phone`, `telegram_chat_id`, `owner_tg_id`,
`district_id`, `address`, `lat`, `lng`, `is_active`, `verified_at`,
`rating` (0–5, manual for v1), `trust_score` (0–1, computed from price freshness +
order fulfillment rate), `working_hours` (JSONB), `payment_methods` (array),
`notes`.

**`shop_delivery_rules`** — `shop_id`, `district_id` (nullable = all), `fee` (numeric),
`free_above` (nullable numeric), `min_order` (numeric), `eta_hours` (int),
`same_day_cutoff` (time), `is_pickup_only` (bool).
A shop can have several rules; resolution picks the most specific district match.

**`shop_products`** (offers — the highest-write table) —
`id`, `shop_id`, `canonical_id` (nullable until matched), `raw_name`, `raw_unit`,
`pack_size` (numeric, e.g. 50 for a 50kg bag), `pack_unit_code`,
`price_per_pack` (numeric(14,2), UZS),
`price_per_base_unit` (numeric(14,4) — **computed on write**, see §5),
`currency` (default `UZS`), `stock_status` (`in_stock|low|on_order|out`),
`min_qty`, `updated_at`, `updated_by` (`shop|admin|import`), `is_active`,
`staleness_state` (`fresh|aging|stale`).
Indexes: `unique(shop_id, canonical_id, pack_size, pack_unit_code)`,
`btree(canonical_id, price_per_base_unit)` ← the query index for quotes,
`btree(updated_at)`, partial index `WHERE is_active AND staleness_state <> 'stale'`.

**`price_history`** — `shop_product_id`, `price_per_pack`, `price_per_base_unit`,
`recorded_at`. Append-only. Used for trend badges ("narx 3 kunda 5% oshdi") and audit.
Partition by month if it grows.

**`import_batches`** + **`import_rows`** — staging for Excel/CSV uploads:
batch status (`uploaded|parsed|awaiting_confirmation|applied|failed`), per-row
`raw_payload` JSONB, `matched_canonical_id`, `match_confidence`, `resolution`
(`auto|manual|skipped`). Never write directly into `shop_products` from an upload.

### 4.3 Demand side

**`users`** — `id`, `tg_id` (unique), `username`, `full_name`, `phone`, `lang`
(`uz_latn|uz_cyrl|ru`), `district_id`, `role` (`customer|shop_owner|admin`),
`is_blocked`, `created_at`, `last_active_at`, `referral_source`.

**`baskets`** — `id`, `user_id`, `raw_text`, `status`
(`parsing|awaiting_confirmation|confirmed|quoted|ordered|abandoned`), `created_at`.

**`basket_lines`** — `id`, `basket_id`, `line_no`, `raw_text`, `parsed_name`,
`qty` (numeric), `unit_code`, `canonical_id` (nullable), `match_confidence`,
`match_method` (`alias|trgm|vector|llm|manual`), `needs_review` (bool),
`user_note`.

**`quotes`** — `id`, `basket_id`, `strategy` (enum, see §7), `items_total`,
`delivery_total`, `grand_total`, `coverage_pct`, `shop_count`, `eta_hours`,
`missing_line_ids` (int[]), `payload` (JSONB — the full immutable snapshot),
`created_at`.
Quotes are **snapshots**. Prices may change; the order must reference the quoted price.

**`orders`** — `id`, `quote_id`, `user_id`, `status`
(`new|confirmed|partially_fulfilled|fulfilled|cancelled`), `contact_phone`,
`delivery_address`, `comment`, `grand_total_quoted`, `grand_total_final`,
`cancel_reason`, timestamps.

**`order_shop_parts`** — one row per shop in the order: `order_id`, `shop_id`,
`subtotal`, `delivery_fee`, `status`, `shop_response`
(`pending|accepted|rejected|partial`), `responded_at`.

**`order_items`** — `order_shop_part_id`, `canonical_id`, `shop_product_id`,
`qty`, `unit_code`, `unit_price_quoted`, `line_total`, `fulfilled_qty`.

### 4.4 Learning / ops

**`unmatched_queries`** — `raw_text`, `normalized`, `user_id`, `occurrences`,
`suggested_canonical_id`, `status` (`new|reviewing|resolved|junk`), `resolved_alias_id`.
**This table is the growth engine of the catalog.** Every unmatched line goes here, gets
deduplicated by normalized text with an incrementing counter, and appears in the admin
queue sorted by frequency.

**`llm_calls`** — `purpose`, `prompt_version`, `input_hash`, `input_tokens`,
`output_tokens`, `cost_usd`, `latency_ms`, `cache_hit`, `created_at`. Needed to keep
LLM cost per basket under control.

**`events`** — lightweight analytics: `user_id`, `name`, `props` JSONB, `created_at`.

---

## 5. Unit normalization (get this right or nothing works)

Every offer must be reduced to a **price per base unit** before comparison. A 50kg cement
bag at 52,000 UZS and a 25kg bag at 28,000 UZS are not comparable until you compute
1,040 vs 1,120 UZS/kg.

```
price_per_base_unit = price_per_pack / (pack_size * factor_to_base(pack_unit))
```

Implement in `domain/pricing/units.py` as pure functions:

- `to_base(qty: Decimal, unit: str) -> Decimal`
- `unit_price(price_per_pack, pack_size, pack_unit, base_unit) -> Decimal`
- `line_cost(required_qty, required_unit, offer) -> LineCost` — must handle **pack
  rounding**: if the customer needs 7 kg of tile adhesive and the shop sells 25 kg bags,
  they buy 1 bag and pay for 25 kg. Return `packs_needed`, `billed_qty`, `overage_qty`,
  `cost`. Never quietly price a fraction of a bag.
- Reject cross-dimension comparisons (kg vs m²) with a typed exception.

Use `Decimal` for all money and quantity math. Never `float`. Round UZS to whole units
at the final total only, using `ROUND_HALF_UP`.

---

## 6. Matching pipeline (deterministic first, LLM last)

`domain/matching/` implements a cascade. Each stage is a pure function taking candidates;
the service layer supplies data from repositories.

**Stage 0 — Normalize** (`domain/normalize/text.py`):
1. Unicode NFKC, lowercase, strip.
2. Cyrillic → Latin transliteration for Uzbek (`ў→o'`, `қ→q`, `ғ→g'`, `ҳ→h`, `ш→sh`,
   `ч→ch`, `я→ya`, …) and a separate Russian transliteration map.
3. Normalize apostrophes: `ʻ ʼ ' ' '` → `'`.
4. Unify units: `кг|kg|kilo|kilogramm → kg`, `дона|dona|шт|sht|pcs → dona`,
   `қоп|qop|мешок|meshok → qop`, `м2|m2|m²|kv.m|кв.м → m2`.
5. Expand/normalize grade patterns: `m 400|м400|М-400|m-400 → m400`;
   sizes `30 х 30|30*30|30х30 → 30x30`; `d12|Ø12|диаметр 12 → d12`.
6. Drop stopwords (`sifatli`, `original`, `aksiya`, `новый`, `качественный`) into a
   separate token bag rather than deleting them silently.
7. Emit `NormalizedQuery(tokens, numbers, units, grades, sizes, raw)`.

**Stage 1 — Exact alias** — hash lookup on `product_aliases.alias_norm`. Confidence 1.0.
Target: ≥70% of production traffic after 2 months. Sub-10ms.

**Stage 2 — Trigram + attribute scoring** — `pg_trgm` similarity over
`canonical_products.search_doc`, take top 20, then re-rank in pure Python:

```
score = 0.45 * trigram_similarity
      + 0.25 * attribute_match      (grade/size/diameter extracted in Stage 0 vs JSONB)
      + 0.15 * brand_match
      + 0.10 * category_prior       (co-occurrence with other lines in same basket)
      + 0.05 * popularity           (log of alias hit_count)
```

Decision thresholds (make these config values, not magic numbers):
- `score >= 0.82` and margin over runner-up `>= 0.12` → **auto-accept**
- `0.55 <= score < 0.82` → **ask the user** with inline buttons showing top 3
- `score < 0.55` → go to Stage 3

**Stage 3 — LLM disambiguation.** Send the normalized query + top 8 candidates (id, name,
brand, attributes) and ask for a single JSON object:
`{"canonical_id": int|null, "confidence": 0.0-1.0, "reason": "..."}`.
Rules:
- Temperature 0, `max_tokens` 300, hard 8s timeout, 2 retries with jitter.
- Cache by `sha256(normalized_query + candidate_id_list + prompt_version)` in Redis
  (30 days) and Postgres.
- **On success, write back a `product_aliases` row** with `source='llm'`,
  `is_approved=false`, and `confidence` from the model. Once an admin approves it, Stage 1
  handles that query forever. The system gets cheaper and faster with use — this feedback
  loop is a required feature, not an optimization.
- Daily token budget cap from config; when exceeded, skip Stage 3 and fall through.

**Stage 4 — Unresolved** → write to `unmatched_queries`, tell the user that item isn't in
the catalog yet, and continue with the rest of the basket. **Never fail the whole basket
because of one unknown line.**

Optional (Phase 6): add `pgvector` embeddings for semantic matches where trigrams fail
(`yopishtiruvchi` → `plitka yelimi`). Insert as Stage 2.5.

---

## 7. Basket parsing

Input examples the parser must handle (write these as test fixtures verbatim):

```
500 dona g'isht, 10 qop cement m400, 3 quti plitka 30x30
цемент м400 - 20 қоп
армaтура 12мм 500 кг
5 rulon ruberoid
Gipsokarton 12.5mm 40 list
kraska belaya 3 vedra 10l
2t qum, 1.5 kub shag'al
```

Pipeline in `domain/parsing/`:
1. **Split into lines** — newline, `;`, `,` (careful: `12,5` is a decimal — protect
   numeric commas first), `•`, `-` at line start, numbered lists.
2. **Extract quantity + unit** with an ordered regex battery. Handle: number before name,
   number after name, `x`/`×` multipliers, ranges (take the upper bound and flag),
   missing unit (→ infer from the matched SKU's base unit and flag `needs_review`).
3. **Extract the product phrase** = remainder after removing qty/unit tokens.
4. Hand each line to the matcher (§6).
5. If the whole message fails structured parsing (< 50% of lines produced a qty), call the
   LLM once with the entire message and a strict JSON schema:
   `{"lines":[{"name":str,"qty":number,"unit":str|null,"confidence":number}]}`.

**Always show the parsed table back to the user for confirmation before quoting.** Silent
guessing on a 40-million-so'm order destroys trust.

---

## 8. Basket optimization (the core algorithm)

`domain/optimizer/`. Pure. Input: a list of `BasketLine` + a list of `Offer` +
`DeliveryRule`s. Output: a list of `QuoteVariant`.

### 8.1 Cost model

```
total(assignment) = Σ_lines line_cost(line, assigned_offer)          # with pack rounding
                  + Σ_shops_used delivery_fee(shop, subtotal, district)
```

where `delivery_fee` is 0 if `subtotal >= free_above`, else the rule's `fee`; and a
shop is only usable if `subtotal >= min_order`.

This is a **capacitated facility-location / set-cover hybrid** — the fixed delivery fee
per shop is exactly what makes naive per-item minimization wrong. Splitting a basket
across 7 shops to save 90,000 UZS on items while paying 7 × 40,000 in delivery is a loss.

### 8.2 Algorithm

Candidate shops per district are few (≤ 60). Solve exactly where you can, heuristically
otherwise:

1. **Prune** — keep only offers that are: fresh (`staleness_state != 'stale'`),
   `is_active`, stock in (`in_stock`,`low`,`on_order`), shop serves the user's district.
   For each `(line, shop)` keep only the cheapest qualifying offer.
2. **Baseline** — best single shop by coverage-then-cost. Always compute; it's also the
   `SINGLE_SHOP` variant.
3. **Greedy construction** — start from the baseline shop set; repeatedly add the shop
   whose marginal saving (items saved − its delivery fee) is largest and positive.
4. **Local search** — until no improvement, or 200 iterations / 500ms budget:
   - *reassign*: move a single line to another already-used shop if it lowers total;
   - *drop*: remove a shop and reassign its lines, if that lowers total;
   - *swap*: exchange one used shop for one unused shop.
5. **Exact check** — if `used_shops ≤ 12`, brute-force all subsets of the candidate shop
   pool restricted to the ≤ 12 most promising shops (`2^12 = 4096`, trivial) and take the
   true optimum. Assert in tests that greedy+local-search reaches the exact optimum on all
   fixtures with ≤ 12 shops.

Deterministic tie-breaking: lower total → fewer shops → higher avg trust_score → lower
shop_id. Same input must always give the same output (test this).

### 8.3 Strategies to produce

| Strategy | Objective |
|---|---|
| `CHEAPEST_TOTAL` | minimize landed total (items + delivery) |
| `SINGLE_SHOP` | one shop, maximize coverage, then minimize cost |
| `FASTEST` | only `in_stock` + `eta_hours <= 24`, then cheapest |
| `PREMIUM` | prefer `tier='premium'`/known brands, then cheapest within tier |
| `BALANCED` | minimize weighted score of min-max normalized (cost .45, eta .20, trust .20, shop_count .15) |

Deduplicate variants: if two strategies produce an identical assignment, show one card
with both labels. Never show the user five identical cards.

### 8.4 Variant output

Each `QuoteVariant` carries: per-shop groups (shop, lines, qty, unit price, line total,
subtotal, delivery fee, ETA), `items_total`, `delivery_total`, `grand_total`,
`coverage_pct`, `missing_lines`, `savings_vs_worst`, `savings_pct`, and per-line
`overage` warnings from pack rounding.

Performance target: **p95 < 1.5s** for a 15-line basket. One query to fetch all offers
(`WHERE canonical_id = ANY(:ids)` + district join), zero N+1, all optimization in memory.

---

## 9. Bot UX (aiogram)

Full i18n from day one: `uz_latn` (default), `uz_cyrl`, `ru`. No hardcoded strings in
handlers — everything through `core/i18n.py`.

### Customer flow

```
/start
 → language select (inline)
 → district select (inline, 2 columns)
 → optional phone (request_contact button) — skippable
 → main menu (ReplyKeyboard):
      🧾 Ro'yxat yuborish
      📦 Buyurtmalarim
      🔍 Mahsulot narxi
      🏪 Do'kon sifatida ulanish
      ⚙️ Sozlamalar
```

**Sending a list** → immediately edit-in a "⏳ Ro'yxat tahlil qilinmoqda…" message →
render the parse table:

```
📋 Ro'yxatingiz (8 ta):

1. ✅ Sement M400 (qop 50kg) — 10 qop
2. ✅ G'isht, qizil, M100 — 500 dona
3. ⚠️ Plitka 30x30 — 3 quti  ← turini tanlang
4. ❌ "Xitoy fanera" — katalogda topilmadi
...

[✏️ Tahrirlash] [➕ Qo'shish] [🗑 O'chirish]
[🔎 Narxlarni hisoblash]
```

- `⚠️` lines open an inline picker with top-3 candidates + "Boshqa" (free-text).
- `❌` lines can be kept as a note for the shop or dropped.
- Editing uses a single message that gets edited, not a growing chat.

**Quote presentation** — one message per variant, navigated with `◀ 1/4 ▶` inline
buttons that edit the same message (never spam 5 messages):

```
💰 ENG TEJAMLI

🏪 Baraka Qurilish (Chilonzor) — 3.2 km
   • Sement M400 × 10 qop ......... 520 000
   • G'isht M100 × 500 dona ....... 675 000
   Jami: 1 195 000 + dostavka 40 000

🏪 Nur Stroy (Yunusobod)
   • Plitka 30x30 × 3 quti ........ 285 000
   Jami: 285 000 + dostavka 0 (bepul 250k+)

──────────────────────────────
Mahsulotlar:      1 480 000 so'm
Dostavka:            40 000 so'm
JAMI:             1 520 000 so'm
✅ 210 000 so'm tejaysiz (12%)
📦 Qamrov: 7/8 mahsulot
🚚 Yetkazish: 1-2 kun

[◀]  1/4  [▶]     [✅ Buni tanlash]
[📄 PDF olish] [🔄 Qayta hisoblash]
```

**Order** → confirm phone + address + comment → create `order` + `order_shop_parts` →
notify each shop's `telegram_chat_id` with an accept/reject inline keyboard → notify the
admin group → give the customer an order number and status tracking.

### Shop owner flow (same bot, role-gated)

```
🏪 Do'kon paneli
   📤 Narxlarni yuklash (Excel/CSV)
   ✏️ Tez narx yangilash        ← "cement m400 52000" one-liner
   📊 Mening mahsulotlarim (paginated, inline edit)
   🔔 Yangi buyurtmalar
   ⚙️ Dostavka sozlamalari
```

Excel upload → `import_batches` → parse with `openpyxl`/`pandas` → auto-match each row →
show a summary ("142 qatordan 118 tasi avtomatik moslashtirildi, 24 tasi tasdiqlashni
kutmoqda") → owner confirms ambiguous rows via inline buttons → only then apply to
`shop_products` + append to `price_history`.

Also accept a plain Excel file forwarded as a document without any command, if the sender
is a verified shop owner.

### Middlewares (order matters)

`ErrorMiddleware` → `LoggingMiddleware(correlation_id)` → `ThrottleMiddleware` →
`DbSessionMiddleware` → `UserContextMiddleware(load user, block check)` →
`I18nMiddleware`.

Throttle: 20 messages/min per user, 3 quote computations/min, 1 Excel upload/5 min.
Use a Redis sliding window. Silently drop, don't reply, when a flood is detected.

---

## 10. Background jobs (`arq`)

| Job | Schedule | Behavior |
|---|---|---|
| `mark_price_staleness` | hourly | `updated_at` > 5d → `aging`; > 7d → `stale` (excluded from quotes) |
| `nudge_shops` | daily 09:00 | DM owners of shops with `aging` prices, one message with a "Yangilash" button |
| `recompute_trust_scores` | daily 03:00 | freshness ratio × 0.5 + accept rate × 0.3 + rating × 0.2 |
| `rollup_metrics` | daily 04:00 | write yesterday's funnel into a `daily_metrics` table |
| `admin_digest` | daily 08:00 | top unmatched queries, stale shop count, orders, GMV |
| `abandon_baskets` | every 30 min | baskets in `awaiting_confirmation` > 24h → `abandoned` |

All jobs idempotent and safe to re-run. Add a Postgres advisory lock per job name.

---

## 11. Admin surface

FastAPI + Jinja2 (server-rendered, no SPA — keep it boring) behind HTTP Basic + IP
allowlist, or a Telegram-login-verified session.

Screens: **Unmatched queue** (sorted by occurrences, one-click "create alias" / "create
SKU" / "mark junk") · **Alias approvals** (LLM-generated, unapproved) · **Shops** (CRUD,
verify, delivery rules) · **Offers** (filter by staleness, bulk deactivate) ·
**Orders** · **Metrics dashboard** · **LLM cost**.

The unmatched queue is the single most important admin screen. Make it fast to work
through: keyboard shortcuts, no page reload per action.

---

## 12. Observability & metrics (instrument in Phase 1, not later)

Log an `events` row for: `basket_submitted`, `parse_completed` (with success rate),
`line_unmatched`, `line_user_resolved`, `quote_generated` (with latency + variant count),
`variant_viewed`, `variant_selected` (with strategy), `order_created`, `order_accepted`,
`shop_price_updated`.

Expose `/metrics` (Prometheus text format) with: quote latency histogram, match-method
distribution, LLM cost counter, stale-price gauge, DB pool gauge.

Track these KPIs from day one — they tell you whether the product works:
`match_rate`, `auto_match_rate`, `avg_lines_per_basket`, `quote→order conversion`,
`price_freshness_pct`, `llm_cost_per_basket`, `strategy_selection_mix`.

---

## 13. Testing requirements

- **Unit** (`tests/unit/`, no DB, < 5s total): unit conversion incl. pack rounding;
  transliteration (uz Cyrillic ↔ Latin round-trip); parser fixtures (all examples in §7
  plus 30 more messy real-world strings); matcher scoring incl. threshold boundaries;
  optimizer — **property tests with `hypothesis`**: total is never below the sum of
  cheapest per-line costs, adding a shop never increases the returned optimum, output is
  deterministic, greedy+local-search equals brute force for ≤ 12 shops.
- **Integration**: repositories against real Postgres; the offer-fetch query for a
  15-line basket must issue ≤ 3 SQL statements (assert with a query counter);
  Excel import end-to-end into staging.
- **E2E**: feed synthetic `Update` objects through the dispatcher with a mocked Bot API;
  cover the whole customer path start → order, and a shop price update.
- **Load**: `locust` or a simple asyncio script — 50 concurrent baskets, assert p95 < 2s.
- Coverage gate: 90% on `app/domain/`, 70% overall. CI fails below.

Seed script (`scripts/seed.py`) must generate a realistic dev dataset: 12 categories,
250 canonical products, 900 aliases, 20 shops, ~4,000 offers with plausible UZS prices,
delivery rules, and 5 sample users. Deterministic (fixed seed) so tests can rely on it.

---

## 14. Agent Operating Rules → save as `CLAUDE.md`

```markdown
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
```

---

## 15. Build phases — prompt the agent one phase at a time

**Phase 0 — Scaffold.** Repo layout per §3, `pyproject.toml` (ruff/mypy/pytest config),
`Makefile` (`install`, `run`, `worker`, `test`, `check`, `migrate`, `seed`),
`docker-compose.yml` (postgres 16 + redis 7 + app + worker), `Dockerfile` (multi-stage,
non-root), `.env.example`, `core/config.py`, `core/logging.py`, FastAPI app with
`/health`, aiogram dispatcher wired to a webhook route, one `/start` handler replying
"ishlaydi". CI workflow. **Deliverable: `docker compose up` works and `/start` answers.**

**Phase 1 — Data layer.** All models from §4, Alembic initial migration with extensions
and every listed index, repositories with typed methods, `scripts/seed.py`,
integration tests. **Deliverable: `make seed` populates a realistic dev DB.**

**Phase 2 — Normalization + units.** `domain/normalize/`, `domain/pricing/`, full unit
tests including transliteration round-trips and pack rounding. Pure, no DB.
**Deliverable: 100% branch coverage on these two packages.**

**Phase 3 — Parser + matcher.** `domain/parsing/`, `domain/matching/` (Stages 0–2 only,
no LLM yet), `catalog_service` wiring trigram search, `unmatched_queries` logging.
**Deliverable: given the §7 fixtures against the seeded catalog, ≥ 85% of lines
auto-match correctly; a `pytest` report prints the match-rate table.**

**Phase 4 — Optimizer.** `domain/optimizer/` with all five strategies, greedy + local
search + brute-force verification, hypothesis property tests, deduplication.
**Deliverable: p95 < 300ms for a 20-line / 40-shop synthetic basket, benchmark in CI.**

**Phase 5 — Customer bot flow.** FSM, i18n catalogs, all middlewares, parse-confirmation
UI with inline editing, variant carousel, order creation, shop notification, e2e tests.
**Deliverable: full start→order path passes e2e.**

**Phase 6 — Supplier side.** Supplier bot panel, Excel/CSV import with staging +
confirmation, quick text price update, delivery rule editing, `price_history`.
**Deliverable: a 150-row Excel imports with a confirmation step and zero direct writes.**

**Phase 7 — LLM fallback.** `llm/` package, Stage 3 disambiguation, whole-message parse
fallback, caching, alias write-back, token budgeting, `llm_calls` accounting.
**Deliverable: match rate improves measurably on a held-out set of 100 messy queries;
cost per basket reported.**

**Phase 8 — Ops.** arq worker + all scheduled jobs, admin panel, `/metrics`, events
analytics, Railway deploy config (web + worker services, health checks, migration on
release), runbook in `docs/OPERATIONS.md`.
**Deliverable: deployed, staleness automation live, admin can clear the unmatched queue.**

**Phase 9 — Hardening.** Load test, index tuning from `EXPLAIN ANALYZE` on the hot quote
query, Sentry, rate-limit tuning, backup/restore script, `docs/README` for onboarding.

---

## 16. Kickoff prompt to paste into Claude Code

```
Read docs/SPEC.md and CLAUDE.md completely before writing anything.

Then execute Phase 0 only.

Before you write code: list the files you will create and the exact dependency versions
you plan to pin, and flag anything in the spec you think is wrong or underspecified.
Wait for my approval on that list.

After approval, implement Phase 0, run `make check`, and stop. Do not start Phase 1.
```
