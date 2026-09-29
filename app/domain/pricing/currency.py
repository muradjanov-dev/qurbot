"""Pure source-currency conversion for prices whose canonical currency is UZS."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

UZS = "UZS"
USD = "USD"
SOURCE_AMOUNT_QUANTUM = Decimal("0.0001")
RATE_QUANTUM = Decimal("0.000001")
UZS_PRICE_QUANTUM = Decimal("0.01")
MAX_SOURCE_AMOUNT = Decimal("999999999999.9999")  # Numeric(16, 4)
MAX_RATE = Decimal("99999999.999999")  # Numeric(14, 6)
MAX_UZS_PRICE = Decimal("999999999999.99")  # Numeric(14, 2)
MAX_BASE_UNIT_PRICE = Decimal("9999999999.9999")  # Numeric(14, 4)


class CurrencyConversionError(ValueError):
    """A source amount cannot be safely represented as its canonical UZS price."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def normalize_currency(currency: str) -> str:
    normalized = currency.strip().upper()
    if normalized not in {UZS, USD}:
        raise CurrencyConversionError("invalid_currency")
    return normalized


def validate_source_amount(amount: Decimal) -> Decimal:
    """Validate an input amount for the Numeric(16, 4) source-price column."""
    if not amount.is_finite() or amount <= 0:
        raise CurrencyConversionError("invalid_amount")
    try:
        normalized = amount.quantize(SOURCE_AMOUNT_QUANTUM)
    except InvalidOperation as exc:
        raise CurrencyConversionError("amount_out_of_range") from exc
    if normalized != amount or normalized > MAX_SOURCE_AMOUNT:
        raise CurrencyConversionError("amount_out_of_range")
    return normalized


def validate_rate(usd_to_uzs_rate: Decimal | None) -> Decimal:
    if usd_to_uzs_rate is None:
        raise CurrencyConversionError("rate_required")
    if not usd_to_uzs_rate.is_finite() or usd_to_uzs_rate <= 0:
        raise CurrencyConversionError("invalid_rate")
    try:
        normalized = usd_to_uzs_rate.quantize(RATE_QUANTUM)
    except InvalidOperation as exc:
        raise CurrencyConversionError("invalid_rate") from exc
    if normalized != usd_to_uzs_rate or normalized > MAX_RATE:
        raise CurrencyConversionError("invalid_rate")
    return normalized


def validate_base_unit_price(amount: Decimal) -> Decimal:
    if not amount.is_finite() or amount < 0:
        raise CurrencyConversionError("invalid_amount")
    try:
        normalized = amount.quantize(Decimal("0.0001"))
    except InvalidOperation as exc:
        raise CurrencyConversionError("amount_out_of_range") from exc
    if normalized != amount or normalized > MAX_BASE_UNIT_PRICE:
        raise CurrencyConversionError("amount_out_of_range")
    return normalized


def convert_to_uzs(
    amount: Decimal,
    *,
    currency: str,
    usd_to_uzs_rate: Decimal | None,
) -> Decimal:
    """Return a positive, Numeric(14, 2)-safe UZS price rounded half up."""
    normalized_currency = normalize_currency(currency)
    source_amount = validate_source_amount(amount)
    if normalized_currency == UZS:
        converted = source_amount
    else:
        rate = validate_rate(usd_to_uzs_rate)
        converted = source_amount * rate

    try:
        canonical = converted.quantize(UZS_PRICE_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise CurrencyConversionError("amount_out_of_range") from exc
    if canonical <= 0:
        raise CurrencyConversionError("invalid_amount")
    if canonical > MAX_UZS_PRICE:
        raise CurrencyConversionError("amount_out_of_range")
    return canonical


def convert_from_uzs(amount_uzs: Decimal, *, usd_to_uzs_rate: Decimal | None) -> Decimal:
    """Convert a canonical UZS amount to a two-decimal USD display amount."""
    if not amount_uzs.is_finite() or amount_uzs < 0 or amount_uzs > MAX_UZS_PRICE:
        raise CurrencyConversionError("invalid_amount")
    rate = validate_rate(usd_to_uzs_rate)
    try:
        return (amount_uzs / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise CurrencyConversionError("amount_out_of_range") from exc
