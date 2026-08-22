"""When a quote variant may be ordered.

The optimiser always returns a variant, even when it could not source a single
line -- that is how the customer is told nothing was found. The checkout used
to accept it anyway, producing an order for 0 items and 0 so'm.
"""

from decimal import Decimal

from app.domain.optimizer.models import BasketItemQuery, OptimizationStrategy, QuoteVariant


def _variant(*, covered: int, total: int, items_total: Decimal = Decimal("0")) -> QuoteVariant:
    missing = tuple(
        BasketItemQuery(
            line_no=i,
            canonical_id=i,
            name_uz="Fanera",
            needed_qty=Decimal("1"),
            unit_code="dona",
        )
        for i in range(total - covered)
    )
    return QuoteVariant(
        strategy_labels=(OptimizationStrategy.CHEAPEST_TOTAL,),
        shop_groups=(),
        items_total_uzs=items_total,
        delivery_total_uzs=Decimal("0"),
        grand_total_uzs=items_total,
        coverage_pct=(covered / total * 100) if total else 0.0,
        covered_count=covered,
        total_count=total,
        missing_lines=missing,
        savings_vs_worst_uzs=Decimal("0"),
        savings_pct=0.0,
        max_eta_hours=24,
    )


def test_variant_covering_nothing_is_not_orderable() -> None:
    assert _variant(covered=0, total=1).is_orderable is False


def test_variant_covering_some_lines_is_orderable() -> None:
    """A partial basket is still worth ordering -- the customer is told what is missing."""
    assert _variant(covered=1, total=3, items_total=Decimal("157000")).is_orderable is True


def test_variant_with_no_lines_at_all_is_not_orderable() -> None:
    assert _variant(covered=0, total=0).is_orderable is False


def test_zero_total_with_covered_lines_is_not_orderable() -> None:
    """Covered but free is not a real quote: every offer priced at zero is a data fault."""
    assert _variant(covered=2, total=2, items_total=Decimal("0")).is_orderable is False
