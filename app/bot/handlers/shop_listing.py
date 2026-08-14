"""Shop product upload wizard.

Design rule for this module: **never hold an answer only in FSM state**. Every
handler writes the owner's answer to shop_product_drafts before it asks the next
question, and photo bytes are persisted on receipt. FSM state records only which
question is open, and even that is recoverable -- `next_missing_step` derives the
next question from the stored draft, so an owner whose session vanished mid-upload
resumes exactly where they stopped with nothing re-typed.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.listing import render_draft_review, render_saved_confirmation
from app.bot.keyboards.listing import (
    get_category_keyboard,
    get_photo_step_keyboard,
    get_resume_keyboard,
    get_review_keyboard,
    get_saved_keyboard,
    get_skip_keyboard,
    get_unit_keyboard,
)
from app.bot.states import ShopListingStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.shop import Shop, ShopProductDraft
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.listing_repo import ListingRepository, draft_to_domain
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.listing import ListingStep, build_listing_card
from app.services.listing_service import ListingService

logger = logging.getLogger(__name__)

router = Router(name="shop_listing")

DRAFT_ID_KEY = "listing_draft_id"

_STEP_STATES: dict[ListingStep, State] = {
    ListingStep.CATEGORY: ShopListingStates.choosing_category,
    ListingStep.NAME: ShopListingStates.entering_name,
    ListingStep.UNIT: ShopListingStates.choosing_unit,
    ListingStep.PRICE: ShopListingStates.entering_price,
    ListingStep.QTY: ShopListingStates.entering_qty,
    ListingStep.DESCRIPTION: ShopListingStates.entering_description,
    ListingStep.PHOTOS: ShopListingStates.uploading_photos,
    ListingStep.REVIEW: ShopListingStates.reviewing,
}

_PHOTO_HINT_KEYS = ("listing_photo_hint_1", "listing_photo_hint_2", "listing_photo_hint_3")


# ── helpers ───────────────────────────────────────────────────────────────


def _services(session: AsyncSession) -> tuple[ListingRepository, ListingService]:
    listing_repo = ListingRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    return listing_repo, ListingService(session, listing_repo, catalog_repo, ops_repo)


async def _get_shop(user: User, session: AsyncSession) -> Shop | None:
    shop_repo = ShopRepository(session)
    if user.tg_id is None:
        return None
    return await shop_repo.get_shop_by_owner_tg_id(user.tg_id)


async def _load_draft(
    state: FSMContext, session: AsyncSession, user: User
) -> ShopProductDraft | None:
    """Fetch the draft from state, falling back to the owner's open draft.

    The fallback is what makes a lost FSM session harmless: if the state no
    longer carries a draft id, the stored draft is still found by owner.
    """
    listing_repo = ListingRepository(session)
    data = await state.get_data()
    draft_id = data.get(DRAFT_ID_KEY)
    if draft_id is not None:
        draft = await listing_repo.get_draft(int(draft_id))
        if draft is not None and draft.status == "draft":
            return draft
    if user.tg_id is None:
        return None
    return await listing_repo.get_open_draft(user.tg_id)


def _parse_decimal(raw: str) -> Decimal | None:
    """Accept the ways people actually type numbers: '52 000', '52.000', '1,5'."""
    cleaned = raw.strip().replace(" ", "").replace(" ", "")
    if not cleaned:
        return None
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


async def _ask_step(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    draft: ShopProductDraft,
    lang: str,
    step: ListingStep,
) -> None:
    """Ask one question and move the FSM to the matching state."""
    await state.set_state(_STEP_STATES[step])
    await state.update_data({DRAFT_ID_KEY: draft.id})

    catalog_repo = CatalogRepository(session)

    match step:
        case ListingStep.CATEGORY:
            roots = await catalog_repo.list_root_categories()
            await message.answer(
                t("listing_step_category", lang=lang),
                reply_markup=get_category_keyboard(roots, lang=lang),
            )
        case ListingStep.NAME:
            await message.answer(t("listing_step_name", lang=lang))
        case ListingStep.UNIT:
            units = await catalog_repo.list_units()
            suggested = await _suggested_unit(session, draft)
            await message.answer(
                t("listing_step_unit", lang=lang),
                reply_markup=get_unit_keyboard(units, lang=lang, suggested=suggested),
            )
        case ListingStep.PRICE:
            pack = _pack_text(draft)
            await message.answer(t("listing_step_price", lang=lang, pack=pack))
        case ListingStep.QTY:
            await message.answer(
                t("listing_step_qty", lang=lang), reply_markup=get_skip_keyboard(lang)
            )
        case ListingStep.DESCRIPTION:
            await message.answer(
                t("listing_step_description", lang=lang), reply_markup=get_skip_keyboard(lang)
            )
        case ListingStep.PHOTOS:
            await _ask_photo(message, draft, lang)
        case ListingStep.REVIEW:
            await _show_review(message, session, draft, lang)


async def _suggested_unit(session: AsyncSession, draft: ShopProductDraft) -> str | None:
    """Pre-select the base unit of whatever the name already matches."""
    if not draft.name.strip():
        return None
    _repo, service = _services(session)
    try:
        match = await service.match_draft(draft)
    except Exception:
        logger.warning("listing_unit_suggestion_failed draft=%s", draft.id, exc_info=True)
        return None
    return match.base_unit if match.canonical_id else None


def _pack_text(draft: ShopProductDraft) -> str:
    size = draft.pack_size or Decimal("1")
    unit = draft.pack_unit_code or "dona"
    return f"{format(size.normalize(), 'f')} {unit}"


async def _ask_photo(message: Message, draft: ShopProductDraft, lang: str) -> None:
    count = len(draft.photos or [])
    if count >= settings.listing_max_photos:
        await message.answer(
            t("listing_photo_limit_reached", lang=lang, max=settings.listing_max_photos)
        )
        return
    hint = t(_PHOTO_HINT_KEYS[min(count, len(_PHOTO_HINT_KEYS) - 1)], lang=lang)
    await message.answer(
        t(
            "listing_step_photo",
            lang=lang,
            n=count + 1,
            hint=hint,
            max=settings.listing_max_photos,
        ),
        reply_markup=get_photo_step_keyboard(lang, has_photos=count > 0),
    )


async def _show_review(
    message: Message, session: AsyncSession, draft: ShopProductDraft, lang: str
) -> None:
    _repo, service = _services(session)
    match = await service.match_draft(draft)
    domain_draft = draft_to_domain(draft)

    card = build_listing_card(
        title=draft.name,
        price_per_pack=draft.price_per_pack or Decimal("0"),
        price_per_base_unit=service._price_per_base_unit(domain_draft, match.base_unit),
        pack_size=draft.pack_size or Decimal("1"),
        pack_unit=draft.pack_unit_code or "dona",
        base_unit=match.base_unit,
        stock_qty=draft.stock_qty,
        description=draft.description,
        photos=domain_draft.photos,
        max_photos=settings.listing_max_photos,
        show_photos=True,
    )
    text = render_draft_review(
        domain_draft, lang=lang, card=card, matched_name=match.canonical_name
    )
    await message.answer(text, reply_markup=get_review_keyboard(lang))


async def _advance(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    draft: ShopProductDraft,
    lang: str,
) -> None:
    """Ask whatever the stored draft says is still missing."""
    step = next_step_for(draft)
    await _ask_step(message, state, session, draft, lang, step)


def next_step_for(draft: ShopProductDraft) -> ListingStep:
    from app.domain.listing import next_missing_step

    return next_missing_step(draft_to_domain(draft))


# ── entry points ──────────────────────────────────────────────────────────


@router.callback_query(F.data == "shp:add_product")
async def cb_add_product(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Inline-panel entry point into the same wizard as the reply button."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await menu_add_product(callback.message, state, user, session, lang)
    await callback.answer()


@router.message(F.text.in_(["➕ Yangi mahsulot", "➕ Янги маҳсулот", "➕ Новый товар"]))
async def menu_add_product(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        await message.answer(t("not_shop_owner", lang=lang))
        return

    shop = await _get_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    listing_repo = ListingRepository(session)
    if user.tg_id is None:
        return
    existing = await listing_repo.get_open_draft(user.tg_id)
    if existing is not None and (existing.name or existing.category_id):
        await state.update_data({DRAFT_ID_KEY: existing.id})
        await message.answer(
            t("listing_resume_found", lang=lang, name=existing.name or "—"),
            reply_markup=get_resume_keyboard(lang),
        )
        return

    draft = existing or await listing_repo.create_draft(shop.id, user.tg_id)
    await session.commit()
    await message.answer(t("listing_intro", lang=lang))
    await _advance(message, state, session, draft, lang)
    await session.commit()


@router.callback_query(F.data == "lst_resume")
async def callback_resume(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await callback.message.answer(t("listing_resumed", lang=lang))
    await _advance(callback.message, state, session, draft, lang)
    await session.commit()
    await callback.answer()


@router.callback_query(F.data.in_({"lst_discard_new", "lst_new"}))
async def callback_start_new(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    listing_repo = ListingRepository(session)
    shop = await _get_shop(user, session)
    if shop is None or user.tg_id is None:
        await callback.answer()
        return

    if callback.data == "lst_discard_new":
        old = await listing_repo.get_open_draft(user.tg_id)
        if old is not None:
            await listing_repo.discard_draft(old)

    draft = await listing_repo.create_draft(shop.id, user.tg_id)
    await session.commit()
    await _advance(callback.message, state, session, draft, lang)
    await session.commit()
    await callback.answer()


@router.callback_query(F.data == "lst_cancel")
async def callback_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    """Leave the wizard without touching the stored draft.

    Cancelling is not discarding: the answers stay in Postgres so the owner can
    pick the listing back up later.
    """
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.answer(t("listing_cancelled", lang=lang))
    await callback.answer()


# ── step: category ────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("lst_cat:"), ShopListingStates.choosing_category)
async def callback_pick_category(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    category_id = int(callback.data.split(":", 1)[1])

    draft = await _load_draft(state, session, user)
    if draft is None:
        await callback.answer()
        return

    catalog_repo = CatalogRepository(session)
    children = await catalog_repo.list_child_categories(category_id)
    if children:
        await callback.message.answer(
            t("listing_step_subcategory", lang=lang),
            reply_markup=get_category_keyboard(children, lang=lang, parent_id=category_id),
        )
        await callback.answer()
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, category_id=category_id)
    await listing_repo.mark_step_visited(draft, ListingStep.CATEGORY)
    await session.commit()

    await _advance(callback.message, state, session, draft, lang)
    await session.commit()
    await callback.answer()


@router.callback_query(F.data == "lst_cat_root", ShopListingStates.choosing_category)
async def callback_category_root(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    catalog_repo = CatalogRepository(session)
    roots = await catalog_repo.list_root_categories()
    await callback.message.answer(
        t("listing_step_category", lang=lang),
        reply_markup=get_category_keyboard(roots, lang=lang),
    )
    await callback.answer()


# ── step: name ────────────────────────────────────────────────────────────


@router.message(ShopListingStates.entering_name, F.text)
async def step_name(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not message.text:
        return
    name = message.text.strip()
    if not name:
        await message.answer(t("listing_err_name_empty", lang=lang))
        return
    if len(name) > settings.listing_max_name_len:
        await message.answer(t("listing_err_name_too_long", lang=lang))
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, name=name)
    await listing_repo.mark_step_visited(draft, ListingStep.NAME)
    await session.commit()

    await _advance(message, state, session, draft, lang)
    await session.commit()


# ── step: unit + pack size ────────────────────────────────────────────────


@router.callback_query(F.data.startswith("lst_unit:"), ShopListingStates.choosing_unit)
async def callback_pick_unit(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    unit_code = callback.data.split(":", 1)[1]

    draft = await _load_draft(state, session, user)
    if draft is None:
        await callback.answer()
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, pack_unit_code=unit_code)
    await session.commit()

    await state.set_state(ShopListingStates.entering_pack_size)
    await callback.message.answer(t("listing_step_pack_size", lang=lang, unit=unit_code))
    await callback.answer()


@router.message(ShopListingStates.entering_pack_size, F.text)
async def step_pack_size(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not message.text:
        return
    value = _parse_decimal(message.text)
    if value is None:
        await message.answer(t("listing_err_number", lang=lang))
        return
    if value <= 0:
        await message.answer(t("listing_err_positive", lang=lang))
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, pack_size=value)
    await listing_repo.mark_step_visited(draft, ListingStep.UNIT)
    await session.commit()

    await _advance(message, state, session, draft, lang)
    await session.commit()


# ── step: price ───────────────────────────────────────────────────────────


@router.message(ShopListingStates.entering_price, F.text)
async def step_price(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not message.text:
        return
    value = _parse_decimal(message.text)
    if value is None:
        await message.answer(t("listing_err_number", lang=lang))
        return
    if value <= 0:
        await message.answer(t("listing_err_positive", lang=lang))
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, price_per_pack=value)
    await listing_repo.mark_step_visited(draft, ListingStep.PRICE)
    await session.commit()

    await _advance(message, state, session, draft, lang)
    await session.commit()


# ── step: quantity ────────────────────────────────────────────────────────


@router.message(ShopListingStates.entering_qty, F.text)
async def step_qty(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not message.text:
        return
    value = _parse_decimal(message.text)
    if value is None:
        await message.answer(t("listing_err_number", lang=lang))
        return
    if value < 0:
        await message.answer(t("listing_err_negative_qty", lang=lang))
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, stock_qty=value)
    await listing_repo.mark_step_visited(draft, ListingStep.QTY)
    await session.commit()

    await _advance(message, state, session, draft, lang)
    await session.commit()


# ── step: description ─────────────────────────────────────────────────────


@router.message(ShopListingStates.entering_description, F.text)
async def step_description(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not message.text:
        return
    text = message.text.strip()
    if len(text) > settings.listing_max_description_len:
        await message.answer(t("listing_err_description_too_long", lang=lang))
        return

    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, description=text)
    await listing_repo.mark_step_visited(draft, ListingStep.DESCRIPTION)
    await session.commit()

    await _advance(message, state, session, draft, lang)
    await session.commit()


# ── step: photos ──────────────────────────────────────────────────────────


@router.message(ShopListingStates.uploading_photos, F.photo)
async def step_photo(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Persist the photo bytes, then record the handle on the draft.

    Bytes first, deliberately: a Telegram file_id is only valid for the bot that
    received it, so treating it as the store of record would mean losing every
    product photo the day the token is rotated.
    """
    draft = await _load_draft(state, session, user)
    if draft is None or not message.photo:
        return

    if len(draft.photos or []) >= settings.listing_max_photos:
        await message.answer(
            t("listing_photo_limit_reached", lang=lang, max=settings.listing_max_photos)
        )
        await _advance(message, state, session, draft, lang)
        await session.commit()
        return

    # message.photo is ordered smallest-first; the last entry is the best
    # resolution Telegram kept for us.
    photo_size = message.photo[-1]
    if photo_size.file_size and photo_size.file_size > settings.listing_max_photo_bytes:
        await message.answer(t("listing_photo_too_big", lang=lang))
        return

    listing_repo = ListingRepository(session)
    if any(p.get("file_unique_id") == photo_size.file_unique_id for p in (draft.photos or [])):
        await message.answer(t("listing_photo_duplicate", lang=lang))
        return

    data = await _download_photo(message, photo_size.file_id)
    if data is None:
        await message.answer(t("listing_err_photo_failed", lang=lang))
        return

    await listing_repo.store_photo_blob(
        file_unique_id=photo_size.file_unique_id,
        file_id=photo_size.file_id,
        data=data,
        shop_id=draft.shop_id,
        width=photo_size.width,
        height=photo_size.height,
    )
    from app.domain.listing import PhotoRef

    pos = len(draft.photos or [])
    await listing_repo.append_photo(
        draft,
        PhotoRef(file_id=photo_size.file_id, file_unique_id=photo_size.file_unique_id, pos=pos),
    )
    await listing_repo.mark_step_visited(draft, ListingStep.PHOTOS)
    await session.commit()

    await message.answer(t("listing_photo_saved", lang=lang, n=pos + 1))

    if len(draft.photos or []) >= settings.listing_max_photos:
        await _ask_step(message, state, session, draft, lang, ListingStep.REVIEW)
    else:
        await _ask_photo(message, draft, lang)
    await session.commit()


async def _download_photo(message: Message, file_id: str) -> bytes | None:
    bot = message.bot
    if bot is None:
        return None
    try:
        file = await bot.get_file(file_id)
        if not file or not file.file_path:
            return None
        buffer = await bot.download_file(file.file_path)
        if buffer is None:
            return None
        return buffer.read()
    except Exception:
        logger.warning("listing_photo_download_failed file_id=%s", file_id, exc_info=True)
        return None


@router.callback_query(F.data == "lst_photos_done", ShopListingStates.uploading_photos)
async def callback_photos_done(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    listing_repo = ListingRepository(session)
    await listing_repo.mark_step_visited(draft, ListingStep.PHOTOS)
    await session.commit()
    await _ask_step(callback.message, state, session, draft, lang, ListingStep.REVIEW)
    await session.commit()
    await callback.answer()


# ── skip (optional steps) ─────────────────────────────────────────────────


@router.callback_query(
    F.data == "lst_skip",
    ShopListingStates.entering_qty,
)
@router.callback_query(
    F.data == "lst_skip",
    ShopListingStates.entering_description,
)
@router.callback_query(
    F.data == "lst_skip",
    ShopListingStates.uploading_photos,
)
async def callback_skip(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    current = await state.get_state()
    step = {
        ShopListingStates.entering_qty.state: ListingStep.QTY,
        ShopListingStates.entering_description.state: ListingStep.DESCRIPTION,
        ShopListingStates.uploading_photos.state: ListingStep.PHOTOS,
    }.get(current or "")
    if step is None:
        await callback.answer()
        return

    listing_repo = ListingRepository(session)
    await listing_repo.mark_step_visited(draft, step)
    await session.commit()

    await _advance(callback.message, state, session, draft, lang)
    await session.commit()
    await callback.answer()


# ── review + save ─────────────────────────────────────────────────────────


@router.callback_query(F.data == "lst_restart", ShopListingStates.reviewing)
async def callback_restart(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Re-ask from the top, keeping every stored answer as the starting point."""
    draft = await _load_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    listing_repo = ListingRepository(session)
    await listing_repo.update_draft(draft, visited_steps=[])
    await session.commit()
    await _advance(callback.message, state, session, draft, lang)
    await session.commit()
    await callback.answer()


@router.callback_query(F.data == "lst_save", ShopListingStates.reviewing)
async def callback_save(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    draft = await _load_draft(state, session, user)
    if draft is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    _repo, service = _services(session)
    try:
        outcome = await service.apply_draft(draft)
    except ValueError:
        # Something required is still blank -- ask for it rather than saving a
        # half-built offer that would quote wrongly.
        await session.rollback()
        await callback.message.answer(t("listing_err_incomplete", lang=lang))
        fresh = await _load_draft(state, session, user)
        if fresh is not None:
            await _advance(callback.message, state, session, fresh, lang)
            await session.commit()
        await callback.answer()
        return

    await session.commit()
    await state.clear()

    await callback.message.answer(
        render_saved_confirmation(outcome.display_name, lang, media_pending=outcome.media_pending),
        reply_markup=get_saved_keyboard(lang),
    )
    await callback.answer()


# ── customer-facing photo viewing ─────────────────────────────────────────


async def send_listing_photos(
    message: Message,
    photos: list[dict[str, Any]],
    session: AsyncSession,
    caption: str | None = None,
) -> bool:
    """Send product photos, preferring the Telegram handle and falling back to bytes.

    The stored blob is what makes this reliable: if a file_id has gone stale the
    photo is re-uploaded from our own copy instead of failing in front of a
    customer.
    """
    if not photos:
        return False
    listing_repo = ListingRepository(session)
    sent = False
    for index, photo in enumerate(photos):
        file_id = str(photo.get("file_id", ""))
        photo_caption = caption if index == 0 else None
        try:
            await message.answer_photo(file_id, caption=photo_caption)
            sent = True
            continue
        except Exception:
            logger.info("listing_photo_file_id_stale file_id=%s -- using stored bytes", file_id)

        blob = await listing_repo.get_photo_blob(str(photo.get("file_unique_id", "")))
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
