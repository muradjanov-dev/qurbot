"""Pebble ("toshcha") rewards — the loyalty currency customers earn.

Pure: the rate is injected, so the caller supplies the configured value and
this stays testable without settings or a database.
"""

from decimal import ROUND_DOWN, Decimal


def pebbles_for_order(order_total_uzs: Decimal, rate: Decimal) -> int:
    """Whole pebbles earned by an order.

    Rounded down, never up: awarding a pebble the customer did not quite earn
    costs real money at redemption time, and a fractional pebble is not
    something the balance can express. A non-positive total earns nothing --
    refunds and corrections must not mint currency.
    """
    if order_total_uzs <= 0 or rate <= 0:
        return 0
    earned = (order_total_uzs * rate).to_integral_value(rounding=ROUND_DOWN)
    return int(earned)
