"""Customer quote presentations include totals without delivery-time promises."""

import re
from decimal import Decimal

import pytest

from app.bot.handlers.customer import _format_quote_card
from app.domain.optimizer.models import (
    LineAssignment,
    OptimizationStrategy,
    QuoteVariant,
    ShopQuoteGroup,
)
from app.web.storefront.quoting import variant_payload


def _variant() -> QuoteVariant:
    line = LineAssignment(
        line_no=1,
        canonical_id=1,
        product_name="Fanera 10 mm",
        shop_id=1,
        shop_name="QurBot",
        offer_id=1,
        needed_qty=Decimal("1"),
        needed_unit="dona",
        pack_size=Decimal("1"),
        pack_unit="dona",
        packs_needed=1,
        billed_qty=Decimal("1"),
        overage_qty=Decimal("0"),
        unit_price_uzs=Decimal("100000"),
        line_cost_uzs=Decimal("100000"),
    )
    group = ShopQuoteGroup(
        shop_id=1,
        shop_name="QurBot",
        district_name="Chilonzor",
        distance_km=None,
        lines=(line,),
        subtotal_uzs=Decimal("100000"),
        delivery_fee_uzs=Decimal("50000"),
        is_free_delivery=False,
        eta_hours=24,
        trust_score=1.0,
    )
    return QuoteVariant(
        strategy_labels=(OptimizationStrategy.CHEAPEST_TOTAL,),
        shop_groups=(group,),
        items_total_uzs=Decimal("100000"),
        delivery_total_uzs=Decimal("50000"),
        grand_total_uzs=Decimal("150000"),
        coverage_pct=100.0,
        covered_count=1,
        total_count=1,
        missing_lines=(),
        savings_vs_worst_uzs=Decimal("0"),
        savings_pct=0.0,
        max_eta_hours=24,
    )


_DELIVERY_TIME = re.compile(
    r"(?:\b\d+\s*(?:[-–]\s*\d+\s*)?(?:soat|соат|час(?:а|ов)?|ч\.?|"
    r"kun|кун|день|дня|дней)\b|\b(?:ertaga|эртага|завтра|tomorrow|"
    r"bugun|бугун|сегодня|today)\b)",
    re.IGNORECASE,
)


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
def test_bot_quote_keeps_totals_and_coverage_without_time_promise(lang: str) -> None:
    rendered = _format_quote_card(_variant(), lang)

    assert "150 000" in rendered
    assert not _DELIVERY_TIME.search(rendered)
    summary_lines = rendered.rsplit("──────────────────────────────", 1)[1].strip().splitlines()
    assert all(line.strip() for line in summary_lines)


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
def test_storefront_quote_payload_omits_delivery_eta(lang: str) -> None:
    payload = variant_payload(_variant(), lang)

    assert payload["grand_total_raw"] == "150000"
    assert "150 000" in payload["grand_total"]
    assert "eta" not in payload
