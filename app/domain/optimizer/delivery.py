from decimal import Decimal

from app.domain.optimizer.models import DeliveryTier


def calculate_shop_delivery_fee(
    rule: DeliveryTier | None,
    subtotal: Decimal,
) -> tuple[Decimal, bool, bool]:
    """Calculate the delivery fee for a shop given the subtotal and the delivery rule.

    Returns:
        (fee_uzs, is_free, is_eligible)
        - fee_uzs: The delivery charge in UZS (Decimal).
        - is_free: True if free delivery condition is met.
        - is_eligible: True if subtotal meets the shop's min_order requirement.
    """
    if rule is None:
        # Default fallback if no explicit rule is configured
        return Decimal("0"), True, True

    # Check minimum order requirement
    is_eligible = subtotal >= rule.min_order_uzs

    # Check free delivery threshold
    if rule.free_above_uzs is not None and subtotal >= rule.free_above_uzs:
        return Decimal("0"), True, is_eligible

    # Standard base delivery fee
    return rule.base_fee_uzs, False, is_eligible
