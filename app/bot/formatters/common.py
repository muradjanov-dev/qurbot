"""Shared display helpers for Telegram output."""

from decimal import ROUND_HALF_UP, Decimal


def format_uzs(amount: Decimal) -> str:
    """Render a UZS amount as '1 520 000'.

    Grouped with spaces rather than commas: a comma is a decimal separator in
    both Uzbek and Russian convention, so '1,520,000' reads wrong to the people
    actually using this bot.
    """
    whole = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{whole:,}".replace(",", " ")


def format_qty(value: Decimal) -> str:
    """Render a quantity without trailing zeros or scientific notation."""
    return format(value.normalize(), "f")
