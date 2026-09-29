from decimal import Decimal

import pytest

from app.web.storefront.pricing import format_money, price_pair, usd_equivalent


@pytest.mark.parametrize(
    ("amount", "currency", "lang", "expected"),
    [
        (Decimal("1234567.50"), "UZS", "uz_cyrl", "1 234 567,50 сўм"),
        (Decimal("1234567.5"), "UZS", "uz_latn", "1 234 567,5 so'm"),
        (Decimal("1234"), "UZS", "ru", "1 234 сум"),
        (Decimal("1234.5"), "USD", "ru", "1 234,50 USD"),
        (Decimal("12.3456"), "EUR", "uz_cyrl", "12,3456 EUR"),
        (None, "UZS", "ru", "—"),
    ],
)
def test_format_money_uses_decimal_grouping_and_currency_precision(
    amount: Decimal | None, currency: str, lang: str, expected: str
) -> None:
    assert format_money(amount, currency, lang) == expected


@pytest.mark.parametrize(
    ("amount", "rate", "expected"),
    [
        (Decimal("11820.48"), Decimal("11820.48"), Decimal("1.00")),
        (Decimal("1"), Decimal("0"), None),
        (Decimal("1"), None, None),
        (None, Decimal("11820.48"), None),
    ],
)
def test_usd_equivalent_requires_a_valid_rate(
    amount: Decimal | None, rate: Decimal | None, expected: Decimal | None
) -> None:
    assert usd_equivalent(amount, rate) == expected


def test_price_pair_keeps_original_usd_source_and_approximates_uzs_source() -> None:
    original = price_pair(
        Decimal("23640.96"),
        rate_uzs_per_usd=Decimal("11820.48"),
        lang="uz_cyrl",
        source_currency="USD",
        source_amount=Decimal("3.25"),
    )
    assert original["price_uzs"] == Decimal("23640.96")
    assert original["price_usd"] == Decimal("3.25")
    assert original["price_usd_label"] == "3,25 USD"
    assert original["price_usd_approximate"] is False

    converted = price_pair(
        Decimal("23640.96"), rate_uzs_per_usd=Decimal("11820.48"), lang="uz_cyrl"
    )
    assert converted["price_usd"] == Decimal("2.00")
    assert converted["price_usd_label"] == "2,00 USD"
    assert converted["price_usd_approximate"] is True

    unknown = price_pair(Decimal("23640.96"), rate_uzs_per_usd=None, lang="uz_cyrl")
    assert unknown["price_usd"] is None
    assert unknown["price_usd_label"] is None
