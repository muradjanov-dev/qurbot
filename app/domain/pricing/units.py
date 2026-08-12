import math
from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import IncompatibleUnitsError, UnknownUnitError
from app.domain.models import LineCost, OfferPricing, UnitDefinition

STANDARD_UNITS: dict[str, UnitDefinition] = {
    # Mass
    "kg": UnitDefinition(
        code="kg", dimension="mass", base_code=None, factor_to_base=Decimal("1.0000")
    ),
    "tonna": UnitDefinition(
        code="tonna", dimension="mass", base_code="kg", factor_to_base=Decimal("1000.0000")
    ),
    "gramm": UnitDefinition(
        code="gramm", dimension="mass", base_code="kg", factor_to_base=Decimal("0.0010")
    ),
    # Count
    "dona": UnitDefinition(
        code="dona", dimension="count", base_code=None, factor_to_base=Decimal("1.0000")
    ),
    "qop": UnitDefinition(
        code="qop", dimension="count", base_code="dona", factor_to_base=Decimal("1.0000")
    ),
    "quti": UnitDefinition(
        code="quti", dimension="count", base_code="dona", factor_to_base=Decimal("1.0000")
    ),
    "rulon": UnitDefinition(
        code="rulon", dimension="count", base_code="dona", factor_to_base=Decimal("1.0000")
    ),
    # Area
    "m2": UnitDefinition(
        code="m2", dimension="area", base_code=None, factor_to_base=Decimal("1.0000")
    ),
    # Volume
    "m3": UnitDefinition(
        code="m3", dimension="volume", base_code=None, factor_to_base=Decimal("1.0000")
    ),
    "litr": UnitDefinition(
        code="litr", dimension="volume", base_code="m3", factor_to_base=Decimal("0.0010")
    ),
    # Length
    "metr": UnitDefinition(
        code="metr", dimension="length", base_code=None, factor_to_base=Decimal("1.0000")
    ),
    "sm": UnitDefinition(
        code="sm", dimension="length", base_code="metr", factor_to_base=Decimal("0.0100")
    ),
    "mm": UnitDefinition(
        code="mm", dimension="length", base_code="metr", factor_to_base=Decimal("0.0010")
    ),
}


def get_unit_def(
    unit: str,
    custom_units: dict[str, UnitDefinition] | None = None,
) -> UnitDefinition:
    registry = custom_units if custom_units is not None else STANDARD_UNITS
    clean_unit = unit.strip().lower()
    if clean_unit not in registry:
        raise UnknownUnitError(clean_unit)
    return registry[clean_unit]


def to_base(
    qty: Decimal,
    unit: str,
    custom_units: dict[str, UnitDefinition] | None = None,
) -> Decimal:
    """Convert a quantity to its canonical base unit (e.g. tonna -> kg, litr -> m3, sm -> metr)."""
    unit_def = get_unit_def(unit, custom_units)
    return qty * unit_def.factor_to_base


def unit_price(
    price_per_pack: Decimal,
    pack_size: Decimal,
    pack_unit: str,
    base_unit: str,
    custom_units: dict[str, UnitDefinition] | None = None,
) -> Decimal:
    """Calculate price per base unit: price_per_pack / (pack_size * factor_to_base)."""
    pack_u = get_unit_def(pack_unit, custom_units)
    base_u = get_unit_def(base_unit, custom_units)

    if pack_u.dimension != base_u.dimension:
        raise IncompatibleUnitsError(
            from_unit=pack_unit,
            to_unit=base_unit,
            from_dim=pack_u.dimension,
            to_dim=base_u.dimension,
        )

    pack_size_in_base = pack_size * pack_u.factor_to_base
    price = price_per_pack / pack_size_in_base
    return price.quantize(Decimal("0.0001"))


def line_cost(
    required_qty: Decimal,
    required_unit: str,
    offer: OfferPricing,
    custom_units: dict[str, UnitDefinition] | None = None,
) -> LineCost:
    """Compute line cost with strict pack rounding.

    If required 7 kg and offer is sold in 25 kg bags, customer buys 1 full bag and pays for 25 kg.
    """
    req_u = get_unit_def(required_unit, custom_units)
    offer_u = get_unit_def(offer.pack_unit, custom_units)

    if req_u.dimension != offer_u.dimension:
        raise IncompatibleUnitsError(
            from_unit=required_unit,
            to_unit=offer.pack_unit,
            from_dim=req_u.dimension,
            to_dim=offer_u.dimension,
        )

    req_base_qty = required_qty * req_u.factor_to_base
    pack_base_size = offer.pack_size * offer_u.factor_to_base

    # Compute number of packs needed (ceiling of req_qty / pack_size)
    packs_ratio = float(req_base_qty / pack_base_size)
    packs_needed = max(1, math.ceil(packs_ratio))

    billed_qty = Decimal(str(packs_needed)) * pack_base_size
    overage_qty = billed_qty - req_base_qty
    cost = Decimal(str(packs_needed)) * offer.price_per_pack

    return LineCost(
        packs_needed=packs_needed,
        billed_qty=billed_qty,
        overage_qty=overage_qty,
        cost=cost,
    )


def round_currency(amount: Decimal) -> Decimal:
    """Round currency to nearest whole UZS using ROUND_HALF_UP."""
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
