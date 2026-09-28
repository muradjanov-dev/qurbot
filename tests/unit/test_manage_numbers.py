"""Offer calculations use the same rounded decimals PostgreSQL will store."""

from decimal import Decimal

import pytest

from app.web.storefront.routers.manage import _offer_pack_size, _offer_price


@pytest.mark.parametrize(
    ("raw", "expected"), [("1.234", "1.23"), ("1.235", "1.24"), ("53000.125", "53000.13")]
)
def test_price_is_normalized_before_base_price_calculation(raw: str, expected: str) -> None:
    assert _offer_price(raw) == Decimal(expected)


def test_pack_is_normalized_before_unit_conversion() -> None:
    assert _offer_pack_size("1.00005") == Decimal("1.0001")
