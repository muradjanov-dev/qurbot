from decimal import Decimal

from app.domain.optimizer.delivery import calculate_shop_delivery_fee
from app.domain.optimizer.models import DeliveryTier


def test_delivery_fee_default_rule() -> None:
    fee, is_free, is_eligible = calculate_shop_delivery_fee(None, Decimal("100000"))
    assert fee == Decimal("0")
    assert is_free is True
    assert is_eligible is True


def test_delivery_fee_standard() -> None:
    rule = DeliveryTier(
        shop_id=1,
        district_id=10,
        base_fee_uzs=Decimal("40000"),
        free_above_uzs=Decimal("500000"),
        min_order_uzs=Decimal("100000"),
        eta_hours=24,
    )
    # Below free_above, meets min_order
    fee, is_free, is_eligible = calculate_shop_delivery_fee(rule, Decimal("250000"))
    assert fee == Decimal("40000")
    assert is_free is False
    assert is_eligible is True


def test_delivery_fee_free_above() -> None:
    rule = DeliveryTier(
        shop_id=1,
        district_id=10,
        base_fee_uzs=Decimal("40000"),
        free_above_uzs=Decimal("500000"),
        min_order_uzs=Decimal("100000"),
        eta_hours=24,
    )
    # Meets free_above threshold (500,000 UZS)
    fee, is_free, is_eligible = calculate_shop_delivery_fee(rule, Decimal("600000"))
    assert fee == Decimal("0")
    assert is_free is True
    assert is_eligible is True


def test_delivery_fee_min_order_ineligible() -> None:
    rule = DeliveryTier(
        shop_id=1,
        district_id=10,
        base_fee_uzs=Decimal("40000"),
        free_above_uzs=Decimal("500000"),
        min_order_uzs=Decimal("100000"),
        eta_hours=24,
    )
    # Below min_order (50,000 < 100,000)
    fee, is_free, is_eligible = calculate_shop_delivery_fee(rule, Decimal("50000"))
    assert fee == Decimal("40000")
    assert is_free is False
    assert is_eligible is False
