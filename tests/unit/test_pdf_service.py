from decimal import Decimal

from app.domain.optimizer.models import (
    LineAssignment,
    OptimizationStrategy,
    QuoteVariant,
    ShopQuoteGroup,
)
from app.services.pdf_service import generate_quote_pdf


def _sample_variant() -> QuoteVariant:
    line = LineAssignment(
        line_no=1,
        canonical_id=1,
        product_name="Qizilqum Sement M400 (50 kg)",
        shop_id=10,
        shop_name="Qurilish Bozori",
        offer_id=100,
        needed_qty=Decimal("10"),
        needed_unit="qop",
        pack_size=Decimal("50"),
        pack_unit="kg",
        packs_needed=10,
        billed_qty=Decimal("500"),
        overage_qty=Decimal("0"),
        unit_price_uzs=Decimal("1040"),
        line_cost_uzs=Decimal("520000"),
    )
    group = ShopQuoteGroup(
        shop_id=10,
        shop_name="Qurilish Bozori",
        district_name="Chilonzor",
        distance_km=3.2,
        lines=(line,),
        subtotal_uzs=Decimal("520000"),
        delivery_fee_uzs=Decimal("15000"),
        is_free_delivery=False,
        eta_hours=4,
        trust_score=0.9,
    )
    return QuoteVariant(
        strategy_labels=(OptimizationStrategy.CHEAPEST_TOTAL,),
        shop_groups=(group,),
        items_total_uzs=Decimal("520000"),
        delivery_total_uzs=Decimal("15000"),
        grand_total_uzs=Decimal("535000"),
        coverage_pct=100.0,
        covered_count=1,
        total_count=1,
        missing_lines=(),
        savings_vs_worst_uzs=Decimal("0"),
        savings_pct=0.0,
        max_eta_hours=4,
    )


def test_generate_quote_pdf_produces_valid_pdf_bytes() -> None:
    pdf_bytes = generate_quote_pdf(_sample_variant(), order_id=42)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500
