"""A quote must survive leaving memory with its money intact.

Variants are stored in `quotes.payload` and sent to the browser as JSON. If a
Decimal degraded to a float anywhere on that trip, the order total would stop
matching the total the customer was shown.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.optimizer.models import (
    BasketItemQuery,
    LineAssignment,
    OptimizationStrategy,
    QuoteVariant,
    ShopQuoteGroup,
)
from app.domain.optimizer.serde import deserialize_variant, serialize_variant


def _variant() -> QuoteVariant:
    line = LineAssignment(
        line_no=1,
        canonical_id=42,
        product_name="Sement M400",
        shop_id=3,
        shop_name="Baraka",
        offer_id=9,
        needed_qty=Decimal("7.5"),
        needed_unit="kg",
        pack_size=Decimal("50"),
        pack_unit="qop",
        packs_needed=1,
        billed_qty=Decimal("50"),
        overage_qty=Decimal("42.5"),
        unit_price_uzs=Decimal("52000.00"),
        line_cost_uzs=Decimal("52000.00"),
    )
    group = ShopQuoteGroup(
        shop_id=3,
        shop_name="Baraka",
        district_name="Chilonzor",
        distance_km=3.2,
        lines=(line,),
        subtotal_uzs=Decimal("52000.00"),
        delivery_fee_uzs=Decimal("40000.00"),
        is_free_delivery=False,
        eta_hours=24,
        trust_score=0.87,
    )
    return QuoteVariant(
        strategy_labels=(OptimizationStrategy.CHEAPEST_TOTAL, OptimizationStrategy.BALANCED),
        shop_groups=(group,),
        items_total_uzs=Decimal("52000.00"),
        delivery_total_uzs=Decimal("40000.00"),
        grand_total_uzs=Decimal("92000.00"),
        coverage_pct=50.0,
        covered_count=1,
        total_count=2,
        missing_lines=(
            BasketItemQuery(
                line_no=2,
                canonical_id=99,
                name_uz="Fanera 10mm",
                needed_qty=Decimal("3"),
                unit_code="dona",
            ),
        ),
        savings_vs_worst_uzs=Decimal("12000.00"),
        savings_pct=11.5,
        max_eta_hours=24,
    )


def test_variant_round_trips_unchanged() -> None:
    assert deserialize_variant(serialize_variant(_variant())) == _variant()


def test_money_crosses_as_text_not_float() -> None:
    payload = serialize_variant(_variant())
    assert payload["grand_total_uzs"] == "92000.00"
    assert payload["shop_groups"][0]["lines"][0]["unit_price_uzs"] == "52000.00"
    assert isinstance(payload["items_total_uzs"], str)


def test_missing_lines_and_labels_survive() -> None:
    restored = deserialize_variant(serialize_variant(_variant()))
    assert [label.value for label in restored.strategy_labels] == [
        "CHEAPEST_TOTAL",
        "BALANCED",
    ]
    assert restored.missing_lines[0].name_uz == "Fanera 10mm"
    assert restored.missing_lines[0].needed_qty == Decimal("3")
