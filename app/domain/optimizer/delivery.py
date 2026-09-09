from decimal import Decimal

from app.domain.optimizer.models import DeliveryTier

DEFAULT_DELIVERY_FEE_UZS = Decimal("50000")
DEFAULT_FREE_DELIVERY_ABOVE_UZS = Decimal("5000000")


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
        # QurBot's public fallback policy. A missing shop-specific row must not
        # silently turn delivery into 0 so'm (which is what customers saw in
        # production before this fallback was defined).
        is_free = subtotal > DEFAULT_FREE_DELIVERY_ABOVE_UZS
        return (Decimal("0") if is_free else DEFAULT_DELIVERY_FEE_UZS), is_free, True

    # Check minimum order requirement
    is_eligible = subtotal >= rule.min_order_uzs

    # Check free delivery threshold
    # "Thresholdgacha" includes the threshold itself: exactly 5,000,000 is
    # still charged, and only an amount strictly above it is free.
    if rule.free_above_uzs is not None and subtotal > rule.free_above_uzs:
        return Decimal("0"), True, is_eligible

    # Standard base delivery fee
    return rule.base_fee_uzs, False, is_eligible
