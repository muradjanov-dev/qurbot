from decimal import Decimal

from app.domain.listing import (
    PhotoRef,
    StockDisplay,
    build_listing_card,
    ordered_photos,
    pack_label,
    stock_display,
)


def _p(uid: str, pos: int) -> PhotoRef:
    return PhotoRef(file_id=f"fid-{uid}", file_unique_id=uid, pos=pos)


# ── photo ordering ────────────────────────────────────────────────────────


def test_photos_are_ordered_by_position() -> None:
    photos = (_p("c", 2), _p("a", 0), _p("b", 1))
    assert [p.file_unique_id for p in ordered_photos(photos, 3)] == ["a", "b", "c"]


def test_duplicate_photos_are_collapsed() -> None:
    photos = (_p("a", 0), _p("a", 1), _p("b", 2))
    assert [p.file_unique_id for p in ordered_photos(photos, 3)] == ["a", "b"]


def test_photos_are_capped_at_max() -> None:
    photos = tuple(_p(f"u{i}", i) for i in range(6))
    assert len(ordered_photos(photos, 3)) == 3


def test_ties_on_position_fall_back_to_arrival_order() -> None:
    photos = (_p("first", 0), _p("second", 0))
    assert [p.file_unique_id for p in ordered_photos(photos, 3)] == ["first", "second"]


def test_no_photos_is_empty() -> None:
    assert ordered_photos((), 3) == ()


# ── stock ─────────────────────────────────────────────────────────────────


def test_counted_zero_stock_overrides_optimistic_status() -> None:
    """A shop claiming 'in_stock' with 0 counted units must not read as available."""
    assert stock_display("in_stock", Decimal("0"), Decimal("5")) is StockDisplay.OUT


def test_counted_low_stock_downgrades_status() -> None:
    assert stock_display("in_stock", Decimal("3"), Decimal("5")) is StockDisplay.LOW


def test_uncounted_stock_falls_back_to_status() -> None:
    assert stock_display("in_stock", None, Decimal("5")) is StockDisplay.IN_STOCK
    assert stock_display("on_order", None, Decimal("5")) is StockDisplay.ON_ORDER
    assert stock_display("out", None, Decimal("5")) is StockDisplay.OUT


def test_unknown_status_is_treated_as_out() -> None:
    assert stock_display("banana", None, Decimal("5")) is StockDisplay.OUT


def test_ample_counted_stock_keeps_in_stock() -> None:
    assert stock_display("in_stock", Decimal("500"), Decimal("5")) is StockDisplay.IN_STOCK


# ── pack label ────────────────────────────────────────────────────────────


def test_pack_label_strips_trailing_zeros() -> None:
    assert pack_label(Decimal("50.0000"), "kg", "kg") == "50 kg"


def test_pack_label_keeps_real_fractions() -> None:
    assert pack_label(Decimal("12.5"), "mm", "mm") == "12.5 mm"


def test_pack_label_falls_back_to_base_unit() -> None:
    assert pack_label(Decimal("1"), "", "dona") == "1 dona"


# ── card assembly ─────────────────────────────────────────────────────────


def test_card_carries_display_fields() -> None:
    card = build_listing_card(
        title="Sement M400",
        price_per_pack=Decimal("52000"),
        price_per_base_unit=Decimal("1040"),
        pack_size=Decimal("50"),
        pack_unit="kg",
        base_unit="kg",
        brand="Qizilqum",
        description="  Original zavod qadog'i  ",
        shop_name="Baraka Qurilish",
        photos=(_p("a", 0),),
    )
    assert card.title == "Sement M400"
    assert card.pack_label == "50 kg"
    assert card.description == "Original zavod qadog'i"
    assert card.has_photos is True
    assert card.primary_photo is not None
    assert card.primary_photo.file_unique_id == "a"


def test_unmoderated_media_is_withheld_but_product_still_renders() -> None:
    """A pending photo must not reach customers -- the product itself still must."""
    card = build_listing_card(
        title="Sement M400",
        price_per_pack=Decimal("52000"),
        price_per_base_unit=Decimal("1040"),
        pack_size=Decimal("50"),
        pack_unit="kg",
        base_unit="kg",
        photos=(_p("a", 0),),
        show_photos=False,
    )
    assert card.photos == ()
    assert card.has_photos is False
    assert card.primary_photo is None
    assert card.title == "Sement M400"
    assert card.price_per_pack == Decimal("52000")


def test_blank_description_becomes_none() -> None:
    card = build_listing_card(
        title="X",
        price_per_pack=Decimal("1"),
        price_per_base_unit=Decimal("1"),
        pack_size=Decimal("1"),
        pack_unit="dona",
        base_unit="dona",
        description="   ",
    )
    assert card.description is None


def test_attributes_are_sorted_and_empties_dropped() -> None:
    card = build_listing_card(
        title="X",
        price_per_pack=Decimal("1"),
        price_per_base_unit=Decimal("1"),
        pack_size=Decimal("1"),
        pack_unit="dona",
        base_unit="dona",
        attributes={"size": "30x30", "grade": "M400", "blank": "", "missing": None},
    )
    assert card.attributes == (("grade", "M400"), ("size", "30x30"))
