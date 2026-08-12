from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Dimension = Literal["mass", "count", "area", "volume", "length"]


@dataclass(frozen=True)
class UnitDefinition:
    code: str
    dimension: Dimension
    base_code: str | None
    factor_to_base: Decimal = Decimal("1.0000")


@dataclass(frozen=True)
class OfferPricing:
    shop_product_id: int
    shop_id: int
    canonical_id: int | None
    raw_name: str
    pack_size: Decimal
    pack_unit: str
    price_per_pack: Decimal
    price_per_base_unit: Decimal


@dataclass(frozen=True)
class LineCost:
    packs_needed: int
    billed_qty: Decimal
    overage_qty: Decimal
    cost: Decimal


@dataclass(frozen=True)
class NormalizedQuery:
    raw: str
    text_norm: str
    tokens: list[str] = field(default_factory=list)
    numbers: list[Decimal] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    grades: list[str] = field(default_factory=list)
    sizes: list[str] = field(default_factory=list)
    stopwords: list[str] = field(default_factory=list)
