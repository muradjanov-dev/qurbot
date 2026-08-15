from decimal import Decimal

import pytest

from app.domain.listing import parse_listing_caption

# ── the happy path: everything in one caption ─────────────────────────────


def test_full_caption_is_parsed() -> None:
    r = parse_listing_caption("Sement M400 50kg qop 52000")
    assert r.name == "Sement M400 qop"
    assert r.pack_size == Decimal("50")
    assert r.pack_unit == "kg"
    assert r.price == Decimal("52000")


def test_grade_digits_are_never_mistaken_for_price() -> None:
    """M400 is a grade, not 400 so'm -- digits glued to letters stay in the name."""
    r = parse_listing_caption("Sement M400 52000 so'm")
    assert r.price == Decimal("52000")
    assert "M400" in r.name


def test_size_pattern_stays_in_the_name() -> None:
    r = parse_listing_caption("Plitka 30x30 quti 285000 so'm")
    assert r.price == Decimal("285000")
    assert "30x30" in r.name


def test_thickness_is_not_treated_as_pack_size() -> None:
    """12.5mm is a product dimension; mm is never how a pack is sold."""
    r = parse_listing_caption("Gipsokarton 12.5mm 45000 so'm")
    assert r.pack_size is None
    assert r.pack_unit is None
    assert r.price == Decimal("45000")
    assert "12.5mm" in r.name


# ── explicit vs inferred price ────────────────────────────────────────────


@pytest.mark.parametrize(
    "caption",
    [
        "Sement M400 52000 so'm",
        "Sement M400 52000 sum",
        "Sement M400 52000 сум",
        "Sement M400 narx 52000",
        "Sement M400 narxi: 52000",
        "Sement M400 = 52000",
        "Цемент М400 цена 52000",
    ],
)
def test_marked_price_is_explicit(caption: str) -> None:
    r = parse_listing_caption(caption)
    assert r.price == Decimal("52000")
    assert r.price_is_explicit is True


def test_bare_trailing_number_is_inferred_not_explicit() -> None:
    """An unlabelled number is a guess, and must be flagged so the bot confirms it."""
    r = parse_listing_caption("Sement M400 50kg qop 52000")
    assert r.price == Decimal("52000")
    assert r.price_is_explicit is False


def test_no_price_at_all() -> None:
    r = parse_listing_caption("Sement M400 50kg qop")
    assert r.price is None
    assert r.price_is_explicit is False


def test_small_bare_number_is_not_taken_as_price() -> None:
    """'40 list' must not become a 40 so'm price -- too small to be real."""
    r = parse_listing_caption("Gipsokarton 40 list")
    assert r.price is None


def test_largest_bare_number_wins_when_several() -> None:
    r = parse_listing_caption("Armatura 500 12000")
    assert r.price == Decimal("12000")
    assert r.price_is_explicit is False


# ── pack size + unit ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("caption", "size", "unit"),
    [
        ("Sement 50kg 52000 so'm", Decimal("50"), "kg"),
        ("Sement 50 kg 52000 so'm", Decimal("50"), "kg"),
        ("Sement 50 кг 52000 so'm", Decimal("50"), "kg"),
        ("Bo'yoq 10 litr 95000 so'm", Decimal("10"), "litr"),
        ("Qum 1 tonna 320000 so'm", Decimal("1"), "tonna"),
        ("Plitka 1.44 m2 85000 so'm", Decimal("1.44"), "m2"),
    ],
)
def test_pack_is_bound_to_its_unit(caption: str, size: Decimal, unit: str) -> None:
    r = parse_listing_caption(caption)
    assert r.pack_size == size
    assert r.pack_unit == unit


def test_dimensional_unit_wins_over_container_word() -> None:
    """'50kg qop' is a 50 kg bag: kg is the measurable unit, qop is packaging."""
    r = parse_listing_caption("Sement 50kg qop 52000 so'm")
    assert r.pack_unit == "kg"
    assert r.pack_size == Decimal("50")


def test_container_unit_used_when_nothing_dimensional() -> None:
    r = parse_listing_caption("G'isht 1 dona 1350 so'm")
    assert r.pack_unit == "dona"
    assert r.pack_size == Decimal("1")


def test_decimal_comma_is_accepted() -> None:
    r = parse_listing_caption("Plitka 1,44 m2 85000 so'm")
    assert r.pack_size == Decimal("1.44")


# ── quantity ──────────────────────────────────────────────────────────────


def test_quantity_marker_is_recognised() -> None:
    r = parse_listing_caption("Sement 50kg qop 52000 so'm qoldiq 120")
    assert r.stock_qty == Decimal("120")
    assert r.price == Decimal("52000")


def test_count_unit_after_a_dimensional_pack_is_quantity() -> None:
    """Once the pack is '50 kg', a following '120 dona' can only mean how many."""
    r = parse_listing_caption("Sement 50kg 52000 so'm 120 dona")
    assert r.pack_size == Decimal("50")
    assert r.pack_unit == "kg"
    assert r.stock_qty == Decimal("120")


def test_no_quantity_is_none() -> None:
    r = parse_listing_caption("Sement 50kg 52000 so'm")
    assert r.stock_qty is None


# ── name extraction ───────────────────────────────────────────────────────


def test_name_drops_consumed_numbers() -> None:
    r = parse_listing_caption("Sement M400 50kg 52000 so'm")
    assert r.name == "Sement M400"


def test_name_is_never_empty_when_text_had_words() -> None:
    r = parse_listing_caption("52000 so'm")
    assert r.name == ""
    assert r.price == Decimal("52000")


def test_multiline_caption_is_handled() -> None:
    r = parse_listing_caption("Sement M400 50kg qop\nnarx 52000\nqoldiq 200")
    assert r.pack_size == Decimal("50")
    assert r.price == Decimal("52000")
    assert r.price_is_explicit is True
    assert r.stock_qty == Decimal("200")


def test_empty_caption_yields_nothing() -> None:
    r = parse_listing_caption("")
    assert r.name == ""
    assert r.price is None
    assert r.pack_size is None
    assert r.stock_qty is None


def test_is_actionable_requires_a_name() -> None:
    assert parse_listing_caption("Sement 50kg 52000 so'm").is_actionable is True
    assert parse_listing_caption("52000").is_actionable is False
