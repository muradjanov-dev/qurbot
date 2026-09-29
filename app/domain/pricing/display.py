"""Locale-neutral monetary number formatting shared by web and bot views."""

from decimal import ROUND_HALF_UP, Decimal

_USD_CENT = Decimal("0.01")


def format_grouped_decimal(
    value: Decimal, *, minimum_fraction: int = 0, force_minimum_fraction: bool = False
) -> str:
    """Group thousands with spaces and use a comma for meaningful decimals."""
    if not value.is_finite():
        raise ValueError("money amount must be finite")

    raw = format(value, "f")
    integer, dot, fraction = raw.partition(".")
    fraction = fraction.rstrip("0") if dot else ""
    if fraction:
        fraction = fraction.ljust(minimum_fraction, "0")
    elif minimum_fraction and force_minimum_fraction:
        fraction = "0" * minimum_fraction

    sign = ""
    if integer.startswith(("-", "+")):
        sign, integer = integer[0], integer[1:]
    groups: list[str] = []
    while integer:
        groups.append(integer[-3:])
        integer = integer[:-3]
    whole = sign + " ".join(reversed(groups or ["0"]))
    return whole + ("," + fraction if fraction else "")


def format_uzs_amount(amount: Decimal) -> str:
    """Format UZS with space groups, retaining cents when they are present."""
    if not amount.is_finite():
        raise ValueError("money amount must be finite")
    exponent = amount.as_tuple().exponent
    minimum_fraction = min(max(-exponent, 0), 2) if isinstance(exponent, int) else 0
    return format_grouped_decimal(amount, minimum_fraction=minimum_fraction)


def usd_equivalent(amount_uzs: Decimal, rate_uzs_per_usd: Decimal | None) -> Decimal | None:
    """Convert a UZS amount at the supplied rate without using floating point."""
    if not amount_uzs.is_finite() or rate_uzs_per_usd is None:
        return None
    if not rate_uzs_per_usd.is_finite() or rate_uzs_per_usd <= 0:
        return None
    return (amount_uzs / rate_uzs_per_usd).quantize(_USD_CENT, rounding=ROUND_HALF_UP)
