from decimal import Decimal

import pytest

from app.core.exceptions import IncompatibleUnitsError, UnknownUnitError
from app.domain.models import OfferPricing
from app.domain.pricing.units import (
    line_cost,
    round_currency,
    to_base,
    unit_price,
)


def test_to_base_conversions() -> None:
    # Mass
    assert to_base(Decimal("50"), "kg") == Decimal("50")
    assert to_base(Decimal("2"), "tonna") == Decimal("2000")
    assert to_base(Decimal("500"), "gramm") == Decimal("0.5")

    # Length
    assert to_base(Decimal("6"), "metr") == Decimal("6")
    assert to_base(Decimal("100"), "sm") == Decimal("1")
    assert to_base(Decimal("12"), "mm") == Decimal("0.012")

    # Volume
    assert to_base(Decimal("10"), "litr") == Decimal("0.01")
    assert to_base(Decimal("2.5"), "m3") == Decimal("2.5")

    # Area & Count
    assert to_base(Decimal("15"), "m2") == Decimal("15")
    assert to_base(Decimal("500"), "dona") == Decimal("500")


def test_unit_price_calculation() -> None:
    # 50kg bag at 52,000 UZS -> 1,040 UZS/kg
    p1 = unit_price(
        price_per_pack=Decimal("52000"),
        pack_size=Decimal("50"),
        pack_unit="kg",
        base_unit="kg",
    )
    assert p1 == Decimal("1040.0000")

    # 25kg bag at 28,000 UZS -> 1,120 UZS/kg
    p2 = unit_price(
        price_per_pack=Decimal("28000"),
        pack_size=Decimal("25"),
        pack_unit="kg",
        base_unit="kg",
    )
    assert p2 == Decimal("1120.0000")

    # 2 ton rebar bundle at 19,600,000 UZS -> 9,800 UZS/kg
    p3 = unit_price(
        price_per_pack=Decimal("19600000"),
        pack_size=Decimal("2"),
        pack_unit="tonna",
        base_unit="kg",
    )
    assert p3 == Decimal("9800.0000")


def test_line_cost_pack_rounding_tile_adhesive() -> None:
    # Customer needs 7 kg of tile adhesive; shop sells 25 kg bags at 42,000 UZS/bag
    offer = OfferPricing(
        shop_product_id=1,
        shop_id=10,
        canonical_id=100,
        raw_name="Ceresit CM 11 (25 kg)",
        pack_size=Decimal("25"),
        pack_unit="kg",
        price_per_pack=Decimal("42000"),
        price_per_base_unit=Decimal("1680.0000"),
    )

    cost_info = line_cost(
        required_qty=Decimal("7"),
        required_unit="kg",
        offer=offer,
    )

    assert cost_info.packs_needed == 1
    assert cost_info.billed_qty == Decimal("25")
    assert cost_info.overage_qty == Decimal("18")
    assert cost_info.cost == Decimal("42000")


def test_line_cost_pack_rounding_cement() -> None:
    # Customer needs 52 kg of cement; shop sells 50 kg bags at 52,000 UZS/bag
    offer = OfferPricing(
        shop_product_id=2,
        shop_id=10,
        canonical_id=101,
        raw_name="Qizilqum Sement M400 (50 kg)",
        pack_size=Decimal("50"),
        pack_unit="kg",
        price_per_pack=Decimal("52000"),
        price_per_base_unit=Decimal("1040.0000"),
    )

    cost_info = line_cost(
        required_qty=Decimal("52"),
        required_unit="kg",
        offer=offer,
    )

    assert cost_info.packs_needed == 2
    assert cost_info.billed_qty == Decimal("100")
    assert cost_info.overage_qty == Decimal("48")
    assert cost_info.cost == Decimal("104000")


def test_line_cost_exact_count_bricks() -> None:
    # Customer needs 500 dona bricks; shop sells 1 dona at 1,350 UZS
    offer = OfferPricing(
        shop_product_id=3,
        shop_id=12,
        canonical_id=102,
        raw_name="G'isht M100",
        pack_size=Decimal("1"),
        pack_unit="dona",
        price_per_pack=Decimal("1350"),
        price_per_base_unit=Decimal("1350.0000"),
    )

    cost_info = line_cost(
        required_qty=Decimal("500"),
        required_unit="dona",
        offer=offer,
    )

    assert cost_info.packs_needed == 500
    assert cost_info.billed_qty == Decimal("500")
    assert cost_info.overage_qty == Decimal("0")
    assert cost_info.cost == Decimal("675000")


def test_line_cost_generic_pack_unit_against_mass_priced_offer() -> None:
    # Customer asks for "10 qop" cement (a generic pack counter, not a real
    # mass unit); shop prices in 50 kg bags. "qop" should map directly to
    # "10 bags of whatever this offer sells", not fail as a dimension
    # mismatch (qop=count vs kg=mass) or get converted through weight.
    offer = OfferPricing(
        shop_product_id=2,
        shop_id=10,
        canonical_id=101,
        raw_name="Qizilqum Sement M400 (50 kg)",
        pack_size=Decimal("50"),
        pack_unit="kg",
        price_per_pack=Decimal("52000"),
        price_per_base_unit=Decimal("1040.0000"),
    )

    cost_info = line_cost(
        required_qty=Decimal("10"),
        required_unit="qop",
        offer=offer,
    )

    assert cost_info.packs_needed == 10
    assert cost_info.billed_qty == Decimal("500")
    assert cost_info.overage_qty == Decimal("0")
    assert cost_info.cost == Decimal("520000")


def test_reject_cross_dimension_comparison() -> None:
    offer = OfferPricing(
        shop_product_id=4,
        shop_id=10,
        canonical_id=103,
        raw_name="Plitka 30x30",
        pack_size=Decimal("1.5"),
        pack_unit="m2",
        price_per_pack=Decimal("95000"),
        price_per_base_unit=Decimal("63333.3333"),
    )

    with pytest.raises(IncompatibleUnitsError) as exc_info:
        line_cost(
            required_qty=Decimal("10"),
            required_unit="kg",  # mass vs area
            offer=offer,
        )

    assert "incompatible dimensions" in str(exc_info.value)


def test_unknown_unit_rejection() -> None:
    with pytest.raises(UnknownUnitError):
        to_base(Decimal("10"), "unknown_xyz_unit")


def test_unit_price_incompatible_dimensions() -> None:
    with pytest.raises(IncompatibleUnitsError):
        unit_price(
            price_per_pack=Decimal("50000"),
            pack_size=Decimal("50"),
            pack_unit="kg",
            base_unit="m2",
        )


def test_round_currency() -> None:
    assert round_currency(Decimal("1520000.49")) == Decimal("1520000")
    assert round_currency(Decimal("1520000.50")) == Decimal("1520001")
    assert round_currency(Decimal("1520000.75")) == Decimal("1520001")


def test_unit_price_count_request_against_physical_pack() -> None:
    # Customer asks "100 dona taxta"; shop prices taxta by weight. One requested
    # "dona" is one pack, so the per-unit price is the pack price -- this used to
    # raise IncompatibleUnitsError and crash the entire quote (production bug).
    price = unit_price(
        price_per_pack=Decimal("46190"),
        pack_size=Decimal("25"),
        pack_unit="kg",
        base_unit="dona",
    )
    assert price == Decimal("46190.0000")


def test_line_cost_count_request_against_physical_pack() -> None:
    offer = OfferPricing(
        shop_product_id=9,
        shop_id=3,
        canonical_id=77,
        raw_name="Taxta 25x100x6000",
        pack_size=Decimal("25"),
        pack_unit="kg",
        price_per_pack=Decimal("46190"),
        price_per_base_unit=Decimal("1847.6000"),
    )

    cost_info = line_cost(
        required_qty=Decimal("100"),
        required_unit="dona",
        offer=offer,
    )

    assert cost_info.packs_needed == 100
    assert cost_info.cost == Decimal("4619000")
