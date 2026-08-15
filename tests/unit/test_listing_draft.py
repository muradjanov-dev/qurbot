from decimal import Decimal

import pytest

from app.core.exceptions import IncompatibleUnitsError
from app.domain.listing import (
    DraftErrorCode,
    ListingDraft,
    ListingStep,
    PhotoRef,
    draft_price_per_base_unit,
    next_missing_step,
    validate_draft,
)

LIMITS = {"max_photos": 3, "max_name_len": 255, "max_description_len": 2000}


def _complete_draft(**overrides: object) -> ListingDraft:
    base: dict[str, object] = {
        "category_id": 4,
        "name": "Sement M400 50kg qop",
        "description": "Original zavod qadog'i",
        "pack_size": Decimal("50"),
        "pack_unit": "kg",
        "price_per_pack": Decimal("52000"),
        "stock_qty": Decimal("120"),
        "photos": (PhotoRef(file_id="a", file_unique_id="ua", pos=0),),
        "visited_steps": frozenset(ListingStep),
    }
    base.update(overrides)
    return ListingDraft(**base)  # type: ignore[arg-type]


# ── validation ────────────────────────────────────────────────────────────


def test_complete_draft_has_no_errors() -> None:
    assert validate_draft(_complete_draft(), **LIMITS) == []


def test_blank_name_is_rejected() -> None:
    errors = validate_draft(_complete_draft(name="   "), **LIMITS)
    assert DraftErrorCode.NAME_EMPTY in errors


def test_overlong_name_is_rejected() -> None:
    errors = validate_draft(_complete_draft(name="x" * 256), **LIMITS)
    assert DraftErrorCode.NAME_TOO_LONG in errors


def test_overlong_description_is_rejected() -> None:
    errors = validate_draft(_complete_draft(description="x" * 2001), **LIMITS)
    assert DraftErrorCode.DESCRIPTION_TOO_LONG in errors


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")])
def test_non_positive_price_is_rejected(price: Decimal) -> None:
    errors = validate_draft(_complete_draft(price_per_pack=price), **LIMITS)
    assert DraftErrorCode.PRICE_NOT_POSITIVE in errors


@pytest.mark.parametrize("pack_size", [Decimal("0"), Decimal("-5")])
def test_non_positive_pack_size_is_rejected(pack_size: Decimal) -> None:
    errors = validate_draft(_complete_draft(pack_size=pack_size), **LIMITS)
    assert DraftErrorCode.PACK_SIZE_NOT_POSITIVE in errors


def test_negative_stock_qty_is_rejected() -> None:
    errors = validate_draft(_complete_draft(stock_qty=Decimal("-1")), **LIMITS)
    assert DraftErrorCode.STOCK_QTY_NEGATIVE in errors


def test_unknown_stock_qty_is_allowed() -> None:
    """NULL stock means 'unknown', which must stay valid -- it is the default for imports."""
    assert validate_draft(_complete_draft(stock_qty=None), **LIMITS) == []


def test_too_many_photos_is_rejected() -> None:
    photos = tuple(PhotoRef(file_id=f"f{i}", file_unique_id=f"u{i}", pos=i) for i in range(4))
    errors = validate_draft(_complete_draft(photos=photos), **LIMITS)
    assert DraftErrorCode.TOO_MANY_PHOTOS in errors


def test_exactly_max_photos_is_allowed() -> None:
    photos = tuple(PhotoRef(file_id=f"f{i}", file_unique_id=f"u{i}", pos=i) for i in range(3))
    assert validate_draft(_complete_draft(photos=photos), **LIMITS) == []


def test_duplicate_photo_is_rejected() -> None:
    """Same file_unique_id twice means the owner re-sent one angle, not two angles."""
    photos = (
        PhotoRef(file_id="a", file_unique_id="same", pos=0),
        PhotoRef(file_id="b", file_unique_id="same", pos=1),
    )
    errors = validate_draft(_complete_draft(photos=photos), **LIMITS)
    assert DraftErrorCode.DUPLICATE_PHOTO in errors


def test_zero_photos_is_allowed() -> None:
    assert validate_draft(_complete_draft(photos=()), **LIMITS) == []


def test_unknown_unit_is_rejected() -> None:
    errors = validate_draft(_complete_draft(pack_unit="parrot"), **LIMITS)
    assert DraftErrorCode.UNKNOWN_UNIT in errors


def test_missing_category_is_allowed() -> None:
    """Category comes from the matched catalogue product, so it is never asked for."""
    assert validate_draft(_complete_draft(category_id=None), **LIMITS) == []


def test_errors_accumulate_rather_than_short_circuit() -> None:
    errors = validate_draft(
        _complete_draft(name="", price_per_pack=Decimal("0"), pack_size=Decimal("0")), **LIMITS
    )
    assert DraftErrorCode.NAME_EMPTY in errors
    assert DraftErrorCode.PRICE_NOT_POSITIVE in errors
    assert DraftErrorCode.PACK_SIZE_NOT_POSITIVE in errors


# ── resume: next missing step ─────────────────────────────────────────────


def test_empty_draft_starts_at_name() -> None:
    empty = ListingDraft(
        category_id=None,
        name="",
        description=None,
        pack_size=None,
        pack_unit=None,
        price_per_pack=None,
        stock_qty=None,
        photos=(),
        visited_steps=frozenset(),
    )
    assert next_missing_step(empty) is ListingStep.NAME


def test_resume_skips_already_answered_steps() -> None:
    draft = ListingDraft(
        category_id=4,
        name="Sement M400",
        description=None,
        pack_size=None,
        pack_unit=None,
        price_per_pack=None,
        stock_qty=None,
        photos=(),
        visited_steps=frozenset({ListingStep.NAME}),
    )
    assert next_missing_step(draft) is ListingStep.UNIT


def test_optional_step_is_skipped_once_visited() -> None:
    """Skipping the description must not trap the wizard on the description step."""
    draft = ListingDraft(
        category_id=4,
        name="Sement M400",
        description=None,
        pack_size=Decimal("50"),
        pack_unit="kg",
        price_per_pack=Decimal("52000"),
        stock_qty=None,
        photos=(),
        visited_steps=frozenset(
            {
                ListingStep.NAME,
                ListingStep.UNIT,
                ListingStep.PRICE,
                ListingStep.QTY,
                ListingStep.DESCRIPTION,
            }
        ),
    )
    assert next_missing_step(draft) is ListingStep.PHOTOS


def test_fully_visited_draft_lands_on_review() -> None:
    assert next_missing_step(_complete_draft()) is ListingStep.REVIEW


def test_required_step_reasked_even_if_visited() -> None:
    """A visited-but-empty required field must be re-asked, never silently accepted."""
    draft = _complete_draft(price_per_pack=None)
    assert next_missing_step(draft) is ListingStep.PRICE


# ── pricing ───────────────────────────────────────────────────────────────


def test_price_per_base_unit_uses_pack_size() -> None:
    """52,000 for a 50kg bag is 1,040 per kg -- the number the optimizer compares on."""
    draft = _complete_draft(
        pack_size=Decimal("50"), pack_unit="kg", price_per_pack=Decimal("52000")
    )
    assert draft_price_per_base_unit(draft, base_unit="kg") == Decimal("1040.0000")


def test_price_per_base_unit_for_count_packs() -> None:
    draft = _complete_draft(
        pack_size=Decimal("1"), pack_unit="dona", price_per_pack=Decimal("1350")
    )
    assert draft_price_per_base_unit(draft, base_unit="dona") == Decimal("1350.0000")


def test_price_per_base_unit_rejects_cross_dimension() -> None:
    draft = _complete_draft(pack_unit="kg")
    with pytest.raises(IncompatibleUnitsError):
        draft_price_per_base_unit(draft, base_unit="m2")


def test_price_per_base_unit_requires_complete_pricing() -> None:
    with pytest.raises(ValueError):
        draft_price_per_base_unit(_complete_draft(price_per_pack=None), base_unit="kg")
