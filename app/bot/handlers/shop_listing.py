"""Shop product upload: one message in, a live offer out.

The intended interaction is a single action -- the owner sends photos with a
caption like "Sement M400 50kg qop 52000 so'm" and the product is created. The
handlers below exist mostly to cover what that caption did *not* say: they ask
for exactly the missing piece and nothing more.

Two rules shape the whole module:

* **Nothing is held only in FSM state.** Every value is written to
  shop_product_drafts as it arrives and photo bytes are persisted on receipt, so
  a restart or a lost session costs at most the question in flight. When state
  is gone the draft is still found by owner id, and the next question is derived
  from the stored draft rather than remembered.
* **A price is never saved on a guess.** A caption that marks the price
  ("52000 so'm") is trusted; a bare trailing number is shown back for one-tap
  confirmation first. A wrong price does not fail loudly -- it quietly wins or
  loses every quote -- so it does not get to be implicit.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_uzs
from app.bot.formatters.listing import render_listing_card, render_saved_confirmation
from app.bot.keyboards.listing import (
    get_pack_keyboard,
    get_price_confirm_keyboard,
    get_saved_keyboard,
)
from app.bot.states import ShopListingStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.shop import Shop, ShopProductDraft
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.listing_repo import ListingRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.listing import (
    ParsedListingInput,
    PhotoRef,
    parse_listing_caption,
)
from app.services.listing_service import ListingService

logger = logging.getLogger(__name__)

router = Router(name="shop_listing")

DRAFT_ID_KEY = "listing_draft_id"

MENU_ADD_PRODUCT = ("➕ Yangi mahsulot", "➕ Янги маҳсулот", "➕ Новый товар")


# ── plumbing ──────────────────────────────────────────────────────────────


def _service(session: AsyncSession) -> ListingService:
    listing_repo = ListingRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    return ListingService(session, listing_repo, catalog_repo, ops_repo)


async def _shop_for(user: User, session: AsyncSession) -> Shop | None:
    if user.tg_id is None:
        return None
    return await ShopRepository(session).get_shop_by_owner_tg_id(user.tg_id)


def _is_shop_owner(user: User) -> bool:
    return user.role in ("shop_owner", "admin")


async def _current_draft(
    state: FSMContext, session: AsyncSession, user: User
) -> ShopProductDraft | None:
    """The draft in play: from FSM if present, otherwise the owner's open one.

    The fallback is what makes a lost session harmless -- the draft is keyed by
    owner in the database, so it is found again with nothing re-typed.
    """
    repo = ListingRepository(session)
    data = await state.get_data()
    draft_id = data.get(DRAFT_ID_KEY)
    if draft_id is not None:
        draft = await repo.get_draft(int(draft_id))
        if draft is not None and draft.status == "draft":
            return draft
    if user.tg_id is None:
        return None
    return await repo.get_open_draft(user.tg_id)


def _parse_number(raw: str) -> Decimal | None:
    parsed = parse_listing_caption(raw)
    if parsed.price is not None:
        return parsed.price
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _pack_text(draft: ShopProductDraft) -> str:
    size = draft.pack_size or Decimal("1")
    return f"{format(size.normalize(), 'f')} {draft.pack_unit_code or 'dona'}"


# ── ingest ────────────────────────────────────────────────────────────────


async def _apply_parsed(
    session: AsyncSession, draft: ShopProductDraft, parsed: ParsedListingInput
) -> None:
    """Persist whatever the caption gave us, without overwriting known values."""
    repo = ListingRepository(session)
    fields: dict[str, Any] = {}
    if parsed.name and not draft.name:
        fields["name"] = parsed.name[: settings.listing_max_name_len]
    if parsed.pack_size is not None and draft.pack_size is None:
        fields["pack_size"] = parsed.pack_size
    if parsed.pack_unit is not None and draft.pack_unit_code is None:
        fields["pack_unit_code"] = parsed.pack_unit
    if parsed.stock_qty is not None and draft.stock_qty is None:
        fields["stock_qty"] = parsed.stock_qty
    if parsed.price is not None and draft.price_per_pack is None:
        fields["price_per_pack"] = parsed.price
    if fields:
        await repo.update_draft(draft, **fields)


async def _continue(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    draft: ShopProductDraft,
    lang: str,
    *,
    price_inferred: bool = False,
) -> None:
    """Ask for the one thing still missing, or save when nothing is."""
    await state.update_data({DRAFT_ID_KEY: draft.id})

    if not draft.name.strip():
        await state.set_state(ShopListingStates.entering_name)
        await message.answer(t("listing_ask_name", lang=lang))
        return

    if draft.pack_size is None or draft.pack_unit_code is None:
        await state.set_state(ShopListingStates.choosing_pack)
        suggestions = await _pack_suggestions(session, draft)
        await message.answer(
            t("listing_ask_pack", lang=lang),
            reply_markup=get_pack_keyboard(suggestions, lang=lang),
        )
        return

    if draft.price_per_pack is None:
        await state.set_state(ShopListingStates.entering_price)
        await message.answer(t("listing_ask_price", lang=lang, name=draft.name))
        return

    if price_inferred:
        await state.set_state(ShopListingStates.confirming_price)
        await message.answer(
            t(
                "listing_confirm_price",
                lang=lang,
                price=format_uzs(draft.price_per_pack),
                pack=_pack_text(draft),
            ),
            reply_markup=get_price_confirm_keyboard(lang),
        )
        return

    await _save(message, state, session, draft, lang)


async def _pack_suggestions(
    session: AsyncSession, draft: ShopProductDraft
) -> list[tuple[Decimal, str]]:
    """Offer the packs this product is actually sold in, most common first.

    Anchoring to real catalogue packs beats free text: it is one tap, and it
    keeps pack sizes consistent across shops so the per-unit comparison is
    like-for-like.
    """
    service = _service(session)
    try:
        match = await service.match_draft(draft, log_unmatched=False)
    except Exception:
        logger.warning("listing_pack_suggestion_failed draft=%s", draft.id, exc_info=True)
        return []

    suggestions: list[tuple[Decimal, str]] = []
    if match.canonical_id is not None:
        repo = ShopRepository(session)
        for size, unit in await repo.common_packs_for_canonical(match.canonical_id, limit=3):
            if (size, unit) not in suggestions:
                suggestions.append((size, unit))
    if not suggestions:
        suggestions = [(Decimal("1"), match.base_unit)]
    return suggestions


async def _save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    draft: ShopProductDraft,
    lang: str,
) -> None:
    service = _service(session)
    draft_id = draft.id
    try:
        outcome = await service.apply_draft(draft)
    except ValueError:
        # Something required is still blank. Roll back, reload the draft by its
        # own id (the rollback detached the instance) and ask for what is
        # missing rather than storing a half-built offer that would misquote.
        await session.rollback()
        fresh = await ListingRepository(session).get_draft(draft_id)
        if fresh is not None:
            await _continue(message, state, session, fresh, lang)
        return

    await session.commit()
    await state.clear()

    product = await ListingRepository(session).get_applied_product(outcome.shop_product_id)
    if product is not None:
        card = await service.build_card(product, viewer_is_owner=True)
        await _send_card_with_photos(message, card, lang)

    await message.answer(
        render_saved_confirmation(outcome.display_name, lang, media_pending=outcome.media_pending),
        reply_markup=get_saved_keyboard(lang),
    )


async def _send_card_with_photos(message: Message, card: Any, lang: str) -> None:
    text = render_listing_card(card, lang=lang, show_shop=False)
    if card.primary_photo is not None:
        try:
            await message.answer_photo(card.primary_photo.file_id, caption=text)
            return
        except Exception:
            logger.info("listing_card_photo_failed -- falling back to text")
    await message.answer(text)


# ── entry: the one-action path ────────────────────────────────────────────


@router.message(F.text.in_(MENU_ADD_PRODUCT))
async def menu_add_product(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not _is_shop_owner(user):
        await message.answer(t("not_shop_owner", lang=lang))
        return
    if await _shop_for(user, session) is None:
        await message.answer(t("no_shop_found", lang=lang))
        return
    await state.set_state(ShopListingStates.quick_entry)
    await message.answer(t("listing_quick_prompt", lang=lang))


@router.message(StateFilter(None, ShopListingStates), F.photo)
async def handle_product_photo(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """A photo from a shop owner is a product listing.

    Album members arrive as separate updates sharing media_group_id, and only
    the first carries the caption. Looking the draft up by that id means the
    later photos attach to the listing the first one started -- no in-memory
    album buffer, and nothing lost if the photos straddle a restart.
    """
    if not _is_shop_owner(user) or not message.photo or user.tg_id is None:
        return
    shop = await _shop_for(user, session)
    if shop is None:
        return

    repo = ListingRepository(session)
    draft: ShopProductDraft | None = None
    if message.media_group_id:
        draft = await repo.get_draft_by_media_group(user.tg_id, message.media_group_id)
    if draft is None:
        # Any still-open draft is the product being worked on right now -- a
        # photo sent while answering a question belongs to it. Saving marks the
        # draft applied, so once a product is finished the next photo correctly
        # starts a new one.
        draft = await _current_draft(state, session, user)
    if draft is None:
        draft = await repo.create_draft(shop.id, user.tg_id)
    if message.media_group_id and not draft.media_group_id:
        await repo.update_draft(draft, media_group_id=message.media_group_id)

    stored = await _store_photo(message, session, draft)
    caption = message.caption or ""
    if caption:
        await _apply_parsed(session, draft, parse_listing_caption(caption))
    await session.commit()

    if not stored and not caption:
        return

    # Later album members only add a photo -- the first one drives the flow.
    if message.media_group_id and not caption and draft.name:
        return

    parsed = parse_listing_caption(caption) if caption else None
    await _continue(
        message,
        state,
        session,
        draft,
        lang,
        price_inferred=bool(parsed and parsed.needs_price_confirmation),
    )
    await session.commit()


@router.message(ShopListingStates.quick_entry, F.text)
async def handle_quick_text(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Text-only entry: same caption grammar, no photos."""
    if not message.text or user.tg_id is None:
        return
    shop = await _shop_for(user, session)
    if shop is None:
        await message.answer(t("no_shop_found", lang=lang))
        return

    repo = ListingRepository(session)
    draft = await _current_draft(state, session, user)
    if draft is None or draft.name:
        draft = await repo.create_draft(shop.id, user.tg_id)

    parsed = parse_listing_caption(message.text)
    await _apply_parsed(session, draft, parsed)
    await session.commit()

    await _continue(
        message,
        state,
        session,
        draft,
        lang,
        price_inferred=parsed.needs_price_confirmation,
    )
    await session.commit()


async def _store_photo(message: Message, session: AsyncSession, draft: ShopProductDraft) -> bool:
    """Persist the bytes first, then record the handle on the draft.

    The bytes are the store of record: a Telegram file_id only works for the bot
    that received it, so relying on it alone would lose every product photo the
    day the token is rotated.
    """
    if not message.photo:
        return False
    if len(draft.photos or []) >= settings.listing_max_photos:
        return False

    size = message.photo[-1]
    if size.file_size and size.file_size > settings.listing_max_photo_bytes:
        return False
    if any(p.get("file_unique_id") == size.file_unique_id for p in (draft.photos or [])):
        return False

    data = await _download(message, size.file_id)
    if data is None:
        return False

    repo = ListingRepository(session)
    await repo.store_photo_blob(
        file_unique_id=size.file_unique_id,
        file_id=size.file_id,
        data=data,
        shop_id=draft.shop_id,
        width=size.width,
        height=size.height,
    )
    await repo.append_photo(
        draft,
        PhotoRef(
            file_id=size.file_id, file_unique_id=size.file_unique_id, pos=len(draft.photos or [])
        ),
    )
    return True


async def _download(message: Message, file_id: str) -> bytes | None:
    bot = message.bot
    if bot is None:
        return None
    try:
        file = await bot.get_file(file_id)
        if not file or not file.file_path:
            return None
        buffer = await bot.download_file(file.file_path)
        return buffer.read() if buffer is not None else None
    except Exception:
        logger.warning("listing_photo_download_failed file_id=%s", file_id, exc_info=True)
        return None


# ── follow-ups: only what the caption missed ──────────────────────────────


@router.message(ShopListingStates.entering_name, F.text)
async def step_name(
    message: Message, state: FSMContext, user: User, session: AsyncSession, lang: str
) -> None:
    draft = await _current_draft(state, session, user)
    if draft is None or not message.text:
        return
    parsed = parse_listing_caption(message.text)
    name = (parsed.name or message.text).strip()[: settings.listing_max_name_len]
    if not name:
        await message.answer(t("listing_err_name_empty", lang=lang))
        return
    await ListingRepository(session).update_draft(draft, name=name)
    await _apply_parsed(session, draft, parsed)
    await session.commit()
    await _continue(
        message, state, session, draft, lang, price_inferred=parsed.needs_price_confirmation
    )
    await session.commit()


@router.callback_query(F.data.startswith("lst_pack:"), ShopListingStates.choosing_pack)
async def callback_pick_pack(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    draft = await _current_draft(state, session, user)
    if draft is None:
        await callback.answer()
        return

    _, size_raw, unit = callback.data.split(":", 2)
    await ListingRepository(session).update_draft(
        draft, pack_size=Decimal(size_raw), pack_unit_code=unit
    )
    await session.commit()
    await _continue(callback.message, state, session, draft, lang)
    await session.commit()
    await callback.answer()


@router.callback_query(F.data == "lst_pack_other", ShopListingStates.choosing_pack)
async def callback_pack_other(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(ShopListingStates.entering_pack_size)
    await callback.message.answer(t("listing_ask_pack_custom", lang=lang))
    await callback.answer()


@router.message(ShopListingStates.entering_pack_size, F.text)
async def step_pack_custom(
    message: Message, state: FSMContext, user: User, session: AsyncSession, lang: str
) -> None:
    draft = await _current_draft(state, session, user)
    if draft is None or not message.text:
        return
    parsed = parse_listing_caption(message.text)
    if parsed.pack_size is None or parsed.pack_unit is None:
        await message.answer(t("listing_err_unit", lang=lang))
        return
    await ListingRepository(session).update_draft(
        draft, pack_size=parsed.pack_size, pack_unit_code=parsed.pack_unit
    )
    await session.commit()
    await _continue(message, state, session, draft, lang)
    await session.commit()


@router.message(ShopListingStates.entering_price, F.text)
async def step_price(
    message: Message, state: FSMContext, user: User, session: AsyncSession, lang: str
) -> None:
    draft = await _current_draft(state, session, user)
    if draft is None or not message.text:
        return
    value = _parse_number(message.text)
    if value is None:
        await message.answer(t("listing_err_number", lang=lang))
        return
    if value <= 0:
        await message.answer(t("listing_err_positive", lang=lang))
        return
    await ListingRepository(session).update_draft(draft, price_per_pack=value)
    await session.commit()
    # Typed in answer to a direct question, so it is not a guess: no confirm.
    await _continue(message, state, session, draft, lang)
    await session.commit()


@router.callback_query(F.data == "lst_price_ok", ShopListingStates.confirming_price)
async def callback_price_ok(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _current_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await callback.message.answer(t("listing_price_hint_explicit", lang=lang))
    await _save(callback.message, state, session, draft, lang)
    await callback.answer()


@router.callback_query(F.data == "lst_price_fix", ShopListingStates.confirming_price)
async def callback_price_fix(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _current_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await ListingRepository(session).update_draft(draft, price_per_pack=None)
    await session.commit()
    await state.set_state(ShopListingStates.entering_price)
    await callback.message.answer(t("listing_ask_price", lang=lang, name=draft.name))
    await callback.answer()


@router.callback_query(F.data == "lst_new")
async def callback_add_another(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(ShopListingStates.quick_entry)
    await callback.message.answer(t("listing_quick_prompt", lang=lang))
    await callback.answer()


@router.callback_query(F.data == "lst_cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """Leave the flow without discarding the draft -- the answers stay stored."""
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.answer(t("listing_cancelled", lang=lang))
    await callback.answer()


# ── customer-facing photo delivery ────────────────────────────────────────


async def send_listing_photos(
    message: Message,
    photos: list[dict[str, Any]],
    session: AsyncSession,
    caption: str | None = None,
) -> bool:
    """Send product photos, preferring the Telegram handle and falling back to bytes.

    The stored blob is what makes this dependable: a stale file_id is re-uploaded
    from our own copy rather than failing in front of a customer.
    """
    if not photos:
        return False
    repo = ListingRepository(session)
    sent = False
    for index, photo in enumerate(photos):
        photo_caption = caption if index == 0 else None
        try:
            await message.answer_photo(str(photo.get("file_id", "")), caption=photo_caption)
            sent = True
            continue
        except Exception:
            logger.info("listing_photo_file_id_stale -- using stored bytes")

        blob = await repo.get_photo_blob(str(photo.get("file_unique_id", "")))
        if blob is None:
            continue
        try:
            await message.answer_photo(
                BufferedInputFile(blob.data, filename=f"{blob.file_unique_id}.jpg"),
                caption=photo_caption,
            )
            sent = True
        except Exception:
            logger.warning("listing_photo_send_failed blob=%s", blob.id, exc_info=True)
    return sent
