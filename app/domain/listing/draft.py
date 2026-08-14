"""Pure logic for a shop owner's in-progress product listing.

A draft is collected one step at a time over Telegram, and every step is
persisted before the next question is asked. Which step to ask next is derived
from the stored draft itself (`next_missing_step`) rather than from FSM state,
so an interrupted wizard resumes exactly where it stopped even if the session
storage was lost entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.domain.pricing.units import get_unit_def, unit_price


class ListingStep(Enum):
    """Ordered wizard steps. Declaration order is the order they are asked in."""

    CATEGORY = "category"
    NAME = "name"
    UNIT = "unit"
    PRICE = "price"
    QTY = "qty"
    DESCRIPTION = "description"
    PHOTOS = "photos"
    REVIEW = "review"


class DraftErrorCode(Enum):
    CATEGORY_MISSING = "category_missing"
    NAME_EMPTY = "name_empty"
    NAME_TOO_LONG = "name_too_long"
    DESCRIPTION_TOO_LONG = "description_too_long"
    UNKNOWN_UNIT = "unknown_unit"
    PACK_SIZE_NOT_POSITIVE = "pack_size_not_positive"
    PRICE_NOT_POSITIVE = "price_not_positive"
    STOCK_QTY_NEGATIVE = "stock_qty_negative"
    TOO_MANY_PHOTOS = "too_many_photos"
    DUPLICATE_PHOTO = "duplicate_photo"


@dataclass(frozen=True)
class PhotoRef:
    """A photo the owner sent.

    `file_id` is a Telegram handle -- cheap to re-send, but scoped to one bot
    token, so it is treated as a cache key and never as the store of record.
    `file_unique_id` is stable across bots and identifies the same image, which
    is what makes duplicate detection possible.
    """

    file_id: str
    file_unique_id: str
    pos: int


@dataclass(frozen=True)
class ListingDraft:
    category_id: int | None
    name: str
    description: str | None
    pack_size: Decimal | None
    pack_unit: str | None
    price_per_pack: Decimal | None
    stock_qty: Decimal | None
    photos: tuple[PhotoRef, ...]
    visited_steps: frozenset[ListingStep]


# Steps whose value may legitimately stay empty once the owner has been asked.
_OPTIONAL_STEPS = frozenset({ListingStep.QTY, ListingStep.DESCRIPTION, ListingStep.PHOTOS})


def validate_draft(
    draft: ListingDraft,
    *,
    max_photos: int,
    max_name_len: int,
    max_description_len: int,
) -> list[DraftErrorCode]:
    """Return every problem with the draft, not just the first one."""
    errors: list[DraftErrorCode] = []

    if draft.category_id is None:
        errors.append(DraftErrorCode.CATEGORY_MISSING)

    if not draft.name.strip():
        errors.append(DraftErrorCode.NAME_EMPTY)
    elif len(draft.name) > max_name_len:
        errors.append(DraftErrorCode.NAME_TOO_LONG)

    if draft.description is not None and len(draft.description) > max_description_len:
        errors.append(DraftErrorCode.DESCRIPTION_TOO_LONG)

    if draft.pack_unit is None:
        errors.append(DraftErrorCode.UNKNOWN_UNIT)
    else:
        try:
            get_unit_def(draft.pack_unit)
        except Exception:
            errors.append(DraftErrorCode.UNKNOWN_UNIT)

    if draft.pack_size is None or draft.pack_size <= 0:
        errors.append(DraftErrorCode.PACK_SIZE_NOT_POSITIVE)

    if draft.price_per_pack is None or draft.price_per_pack <= 0:
        errors.append(DraftErrorCode.PRICE_NOT_POSITIVE)

    if draft.stock_qty is not None and draft.stock_qty < 0:
        errors.append(DraftErrorCode.STOCK_QTY_NEGATIVE)

    if len(draft.photos) > max_photos:
        errors.append(DraftErrorCode.TOO_MANY_PHOTOS)

    unique_ids = [p.file_unique_id for p in draft.photos]
    if len(set(unique_ids)) != len(unique_ids):
        errors.append(DraftErrorCode.DUPLICATE_PHOTO)

    return errors


def _step_has_value(draft: ListingDraft, step: ListingStep) -> bool:
    match step:
        case ListingStep.CATEGORY:
            return draft.category_id is not None
        case ListingStep.NAME:
            return bool(draft.name.strip())
        case ListingStep.UNIT:
            return draft.pack_unit is not None and draft.pack_size is not None
        case ListingStep.PRICE:
            return draft.price_per_pack is not None
        case ListingStep.QTY:
            return draft.stock_qty is not None
        case ListingStep.DESCRIPTION:
            return bool(draft.description)
        case ListingStep.PHOTOS:
            return bool(draft.photos)
        case ListingStep.REVIEW:
            return False


def next_missing_step(draft: ListingDraft) -> ListingStep:
    """The step to ask next, derived purely from what the draft already holds.

    A required step is re-asked whenever its value is missing, even if it was
    visited before -- that is what makes a half-finished draft safe to resume
    rather than silently saving an incomplete listing.
    """
    for step in ListingStep:
        if step is ListingStep.REVIEW:
            break
        if _step_has_value(draft, step):
            continue
        if step in _OPTIONAL_STEPS and step in draft.visited_steps:
            continue
        return step
    return ListingStep.REVIEW


def draft_price_per_base_unit(draft: ListingDraft, base_unit: str) -> Decimal:
    """Price per base unit for this draft -- the figure every quote compares on.

    Raises IncompatibleUnitsError when the pack unit cannot express the base
    unit (SPEC §5), rather than storing a silently wrong number.
    """
    if draft.price_per_pack is None or draft.pack_size is None or draft.pack_unit is None:
        raise ValueError("draft pricing is incomplete: need price, pack size and pack unit")
    return unit_price(
        price_per_pack=draft.price_per_pack,
        pack_size=draft.pack_size,
        pack_unit=draft.pack_unit,
        base_unit=base_unit,
    )
