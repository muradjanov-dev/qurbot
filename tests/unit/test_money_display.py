from decimal import Decimal

import pytest

from app.domain.pricing.display import format_grouped_decimal, format_uzs_amount


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("0"), "0"),
        (Decimal("1234"), "1 234"),
        (Decimal("100000.00"), "100 000"),
        (Decimal("1234567.8900"), "1 234 567,89"),
        (Decimal("1234.50"), "1 234,50"),
        (Decimal("-1234.50"), "-1 234,50"),
    ],
)
def test_format_uzs_amount_preserves_cents_and_groups_with_spaces(
    amount: Decimal, expected: str
) -> None:
    assert format_uzs_amount(amount) == expected


def test_format_grouped_decimal_supports_fixed_usd_precision() -> None:
    assert format_grouped_decimal(Decimal("1234.5"), minimum_fraction=2) == "1 234,50"
    assert format_grouped_decimal(Decimal("1234.567"), minimum_fraction=2) == "1 234,567"


def test_non_finite_money_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        format_uzs_amount(Decimal("NaN"))
