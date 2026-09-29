from decimal import Decimal

import pytest

from app.domain.pricing.currency import (
    CurrencyConversionError,
    convert_from_uzs,
    convert_to_uzs,
    validate_base_unit_price,
)


def test_usd_source_price_converts_to_canonical_uzs_to_two_decimals() -> None:
    assert convert_to_uzs(
        Decimal("4.80"), currency="USD", usd_to_uzs_rate=Decimal("11820.48")
    ) == Decimal("56738.30")


def test_uzs_source_price_is_identity_rounded_to_canonical_scale() -> None:
    assert convert_to_uzs(Decimal("1250.345"), currency="UZS", usd_to_uzs_rate=None) == Decimal(
        "1250.35"
    )


@pytest.mark.parametrize(
    "amount", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_source_amount_is_rejected(amount: Decimal) -> None:
    with pytest.raises(CurrencyConversionError, match="invalid_amount"):
        convert_to_uzs(amount, currency="UZS", usd_to_uzs_rate=None)


def test_usd_price_requires_a_positive_rate() -> None:
    with pytest.raises(CurrencyConversionError, match="rate_required"):
        convert_to_uzs(Decimal("2"), currency="USD", usd_to_uzs_rate=None)

    with pytest.raises(CurrencyConversionError, match="invalid_rate"):
        convert_to_uzs(Decimal("2"), currency="USD", usd_to_uzs_rate=Decimal("0"))


def test_canonical_uzs_price_can_be_shown_as_approximate_usd() -> None:
    assert convert_from_uzs(Decimal("56738.30"), usd_to_uzs_rate=Decimal("11820.48")) == Decimal(
        "4.80"
    )


def test_unknown_currency_is_rejected() -> None:
    with pytest.raises(CurrencyConversionError, match="invalid_currency"):
        convert_to_uzs(Decimal("2"), currency="EUR", usd_to_uzs_rate=Decimal("11820.48"))


def test_canonical_uzs_bound_matches_numeric_14_2() -> None:
    assert convert_to_uzs(
        Decimal("999999999999.99"), currency="UZS", usd_to_uzs_rate=None
    ) == Decimal("999999999999.99")

    with pytest.raises(CurrencyConversionError, match="amount_out_of_range"):
        convert_to_uzs(Decimal("1000000000000"), currency="UZS", usd_to_uzs_rate=None)


def test_base_unit_price_bound_matches_numeric_14_4() -> None:
    assert validate_base_unit_price(Decimal("9999999999.9999")) == Decimal("9999999999.9999")

    with pytest.raises(CurrencyConversionError, match="amount_out_of_range"):
        validate_base_unit_price(Decimal("10000000000"))
