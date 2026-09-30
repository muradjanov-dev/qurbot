# Tezqur operator UX and unified Telegram account implementation plan

Spec: the user's approved plan in this conversation, reproduced as requirements below.
Goal: integrate operator chat into the admin design, improve navigation, and use one Telegram account without repeated onboarding.
Stack: existing FastAPI, Jinja, JavaScript, SQLAlchemy, PostgreSQL, Redis and aiogram.

## Global Constraints

- Light theme, green accent, compact existing admin design; uz_cyrl, uz_latn and ru; preserve saved language.
- Keep /operator and existing chat APIs, admin authorization, CSRF, claim/close/request-resolution permissions and message request-id deduplication.
- Desktop: admin navigation, approximately 300px inbox and flexible thread; mobile: inbox then thread, independent scrolling and visible composer with keyboard.
- Persistent dashboard-back and customer-site links; mobile list-back; no URL editing needed.
- Poll every 3 seconds; preserve drafts, focus and scroll; hidden or offscreen threads never marked read; show new-message jump while reading older messages.
- Search server-side by name, username or exact internal customer ID. Optional q max100, trimmed, literal case-insensitive substring for names; numeric exact customer ID; existing scope/after_id and 50-row pagination remain.
- Telegram only: no SMS, email/password, new registration form, separate database or migration. Catalog/cart public, new order needs verified Telegram identity.
- Ordinary /start shows the saved-language main menu without forced language/district/phone. Preserve cart, addresses and orders; explicit re-registration stays intentional.
- Same repository upsert for web and bot; unique tg_id is authoritative. Concurrent creation returns one row, preserves existing language/role/blocked/test flags. No matching by name/phone.
- Existing browser-bound Telegram approval and guest-cart receipt/merge rules remain, including larger quantity rather than addition and cart review before order.
- All child agents gpt-6-luna/max, no nested agents. Parallel disjoint ownership; root owns shared layout, integration, reviews and release.
- No PR: reviewed checked master-based commits, backup then existing CI/deploy to master; verify exact web/worker SHA and /ready. Production never used for test fixtures or a second live bot.

## Task 1: Operator client and layout

Own operator.html, operator.js; create dedicated operator.css loaded by template; relevant localized keys only in core/i18n.py or a dedicated operator strings module; new scoped UI behavior tests. Do not edit base.html, admin.css, deps.py, shared backend or middleware.

- Remove operator's suppression of the shared site header; parent enables admin surface and active chats.
- Implement compact inbox/thread, search and filters, readable names/previews/times/unread markers, selected-row state, loading/empty/error states and selected-thread-only composer. Claim/close/resolution remain authorized and clear.
- Dashboard-back always visible, mobile inbox-back preserves per-conversation draft. Existing conversation deep links continue to select the requested conversation.
- Search sends q after300ms debounce, resets pagination; late responses for old query/filter are ignored. More pages retain q/scope.
- Restrict viewport fitting to chat workspace instead of body. Support admin header/sidebar and mobile keyboard, safe areas and 320/390px widths.
- Preserve 3s foreground polling, no focus loss, draft loss or scroll jumps. Show jump-to-new messages when away from bottom.
- Mark read only if page foreground, thread visibly open (mobile must be in thread view), latest messages in view, not sending/awaiting ownership refresh. Offscreen/list-only/hidden cases leave unread state untouched.
- Test red then green for behavioral regressions with executable real JS/browser; inspect responsive visuals after parent integrates admin frame. Commit owned files, report commands and warnings.

## Task 2: Bot Start and shared repository adapter

Own bot/handlers/common.py ordinary cmd_start section and bot/middlewares/user_context.py; relevant start/middleware/registration tests. Do not edit repository, web auth, other child files or shared layouts.

- Ordinary /start and existing aliases open saved-language welcome/main menu for new and returning users, including users with no district. Clear transient FSM only; no cart/address/order deletion or preference changes.
- Call existing UserRepository.upsert_user(tg_id, username, full_name, lang, referral_source) from middleware instead of independent creation, retaining blocked-user rejection and existing data injection. Task3 makes that existing method atomic; interface unchanged.
- Keep /start login_ handling priority, browser consent and FSM preservation; existing explicit reset/register/reregister and settings/address flows stay available.
- Regression tests: new/existing/no-district users, three languages/admin menu, Start preserves cart/addresses/orders; blocked middleware denies; login deep links preserve approval/FSM; explicit re-registration retains current intended reset semantics.
- Verify focused and project checks on owned branch, commit owned files, report command/output/warnings.

## Task 3: Backend search and atomic account creation

Own services/conversation_service.py queue only, storefront/routers/chat.py queue endpoint only, db/repositories/user_repo.py; new queue-search and user-upsert tests (including real PostgreSQL races). Do not edit bot middleware/start, frontend or shared deps/layout.

- Add q optional parameter to GET /api/chat/operator and ConversationService.queue(admin, after_id=0, scope='all', q=''). Filter before50-row limit; preserve scopes, ascending-ID cursor, permissions and existing response fields.
- Names/usernames use escaped literal substring case-insensitive matching; numeric q matches internal user.id exactly. Empty/whitespace means existing queue. API bounds q to100 chars.
- Make existing upsert_user signature concurrency-safe using existing unique tg_id, supporting production PostgreSQL and SQLite tests, and route web/bot through it without altering authentication proof or transaction ownership.
- Preserve existing language/admin/blocked/test flags when updating identity metadata, and return the persistent row after concurrent creation. No schema change or private contacts in queue payload.
- Tests: scope isolation, names/usernames/Cyrillic/literal wildcard/numeric exact ID, empty query and pagination past50 rows, client denial/CSRF unchanged; simultaneous creation, existing identity preferences/permissions/blocked flag preserved, unrelated transaction changes not lost on uniqueness conflict.
- Run focused checks and real isolated PostgreSQL concurrency tests, commit only owned files and report evidence.

## Task 4: Shared admin frame and navigation (root)

- Recognize exact /operator as admin surface in deps, active chats; use correct breadcrumb label. Keep /chat public storefront.
- Add always-visible customer-site link to admin topbar (/catalog/all, same tab), dashboard-back on operator and reciprocal existing manage link on admin customer view. Customers list remains /manage/users.
- Adjust shared admin chrome for operator viewport without harming other admin pages, compact mobile nav and accessibility.
- Meaningful rendering/permission regressions plus browser desktop/320/390 widths with all child code integrated; commit root-owned files.

## Task 5: Integration, review and release (root)

- Preserve separate child branches, cherry-pick verified owned commits; fresh task reviews and one whole-branch review, fix real findings before release.
- make check with isolated PostgreSQL/Redis; actual browser chat, search, scrolling, drafts, read receipts, mobile keyboard, navigation and guest/customer/admin auth; embedded Telegram authentication regression.
- Stage with dummy bot credentials/isolated data only. No real customer messages. Check legacy Start/reset and checkout/cart receipt regressions.
- Production backup verified via pg_restore list; code-bearing reviewed release commit prevents docs-only CI bypass; push master without PR/force.
- Verify CI success, exact web/worker image SHA, /ready DB/Redis, migration0027 unchanged, worker scheduling, guest/admin navigation and unchanged historical order prices. Preserve review evidence, clean only owned worktrees.
