"""Customer price labels for UZS catalogue prices and their USD equivalent."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.domain.pricing.display import (
    format_grouped_decimal,
    format_uzs_amount,
)
from app.domain.pricing.display import (
    usd_equivalent as _usd_equivalent,
)

_USD_CENT = Decimal("0.01")


def _decimal(value: Decimal | str | int | None) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() else None


def format_money(
    amount: Decimal | str | int | None,
    currency: str,
    lang: str,
) -> str:
    """Format a monetary amount without converting it through a float.

    USD uses two decimal places. UZS keeps meaningful fractional digits while
    dropping insignificant trailing zeroes. Both use a space for thousands
    and a comma for the decimal separator.
    """
    value = _decimal(amount)
    if value is None:
        return "—"

    code = currency.upper()
    if code == "USD":
        value = value.quantize(_USD_CENT, rounding=ROUND_HALF_UP)
        number = format_grouped_decimal(value, minimum_fraction=2, force_minimum_fraction=True)
        return f"{number} USD"

    if code == "UZS":
        number = format_uzs_amount(value)
        label = {"ru": "сум", "uz_cyrl": "сўм", "uz_latn": "so'm"}.get(lang, "сўм")
        return f"{number} {label}"
    return f"{format_grouped_decimal(value)} {code}"


def usd_equivalent(
    amount_uzs: Decimal | str | int | None,
    rate_uzs_per_usd: Decimal | str | int | None,
) -> Decimal | None:
    """Return a two-decimal USD equivalent, or None when no rate is known."""
    amount = _decimal(amount_uzs)
    rate = _decimal(rate_uzs_per_usd)
    if amount is None:
        return None
    return _usd_equivalent(amount, rate)


def price_pair(
    amount_uzs: Decimal | str | int | None,
    *,
    rate_uzs_per_usd: Decimal | str | int | None,
    lang: str,
    source_currency: str = "UZS",
    source_amount: Decimal | str | int | None = None,
) -> dict[str, Any]:
    """Build display labels while keeping UZS as the canonical price.

    USD-origin offers retain their original USD price. Other offers show an
    approximate conversion only when the current rate exists.
    """
    uzs = _decimal(amount_uzs)
    source = source_currency.upper()
    if source == "USD" and _decimal(source_amount) is not None:
        usd = _decimal(source_amount)
        approximate = False
    else:
        usd = usd_equivalent(uzs, rate_uzs_per_usd)
        approximate = usd is not None
    return {
        "price_uzs": uzs,
        "price_usd": usd,
        "price_uzs_label": format_money(uzs, "UZS", lang),
        "price_usd_label": format_money(usd, "USD", lang) if usd is not None else None,
        "price_usd_approximate": approximate,
        "price_source_currency": source,
    }
