from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class OptimizationStrategy(StrEnum):
    CHEAPEST_TOTAL = "CHEAPEST_TOTAL"
    SINGLE_SHOP = "SINGLE_SHOP"
    FASTEST = "FASTEST"
    PREMIUM = "PREMIUM"
    BALANCED = "BALANCED"


@dataclass(frozen=True, slots=True)
class ShopOffer:
    """Pure domain representation of a shop's offer for a canonical product."""

    offer_id: int
    shop_id: int
    shop_name: str
    canonical_id: int
    price_uzs: Decimal
    pack_size: Decimal
    pack_unit: str
    in_stock: bool
    stock_status: str  # in_stock, low, on_order, out_of_stock
    staleness_state: str  # fresh, aging, stale
    tier: str  # economy, standard, premium
    brand_name: str | None
    trust_score: float
    eta_hours: int
    is_active: bool
    district_id: int | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True, slots=True)
class DeliveryTier:
    """Pure domain representation of a shop's delivery rule for a district."""

    shop_id: int
    district_id: int
    base_fee_uzs: Decimal
    free_above_uzs: Decimal | None
    min_order_uzs: Decimal
    eta_hours: int


@dataclass(frozen=True, slots=True)
class BasketItemQuery:
    """A single requirement in the customer's basket to be fulfilled."""

    line_no: int
    canonical_id: int
    name_uz: str
    needed_qty: Decimal
    unit_code: str  # Base or transaction unit


@dataclass(frozen=True, slots=True)
class LineAssignment:
    """Assignment of a single basket line to a shop's offer."""

    line_no: int
    canonical_id: int
    product_name: str
    shop_id: int
    shop_name: str
    offer_id: int
    needed_qty: Decimal
    needed_unit: str
    pack_size: Decimal
    pack_unit: str
    packs_needed: int
    billed_qty: Decimal
    overage_qty: Decimal
    unit_price_uzs: Decimal
    line_cost_uzs: Decimal


@dataclass(frozen=True, slots=True)
class ShopQuoteGroup:
    """A collection of line items assigned to a single shop within a quote variant."""

    shop_id: int
    shop_name: str
    district_name: str | None
    distance_km: float | None
    lines: tuple[LineAssignment, ...]
    subtotal_uzs: Decimal
    delivery_fee_uzs: Decimal
    is_free_delivery: bool
    eta_hours: int
    trust_score: float

    @property
    def shop_total_uzs(self) -> Decimal:
        return self.subtotal_uzs + self.delivery_fee_uzs


@dataclass(frozen=True, slots=True)
class QuoteVariant:
    """A complete optimized quote solution representing one or more strategies."""

    strategy_labels: tuple[OptimizationStrategy, ...]
    shop_groups: tuple[ShopQuoteGroup, ...]
    items_total_uzs: Decimal
    delivery_total_uzs: Decimal
    grand_total_uzs: Decimal
    coverage_pct: float
    covered_count: int
    total_count: int
    missing_lines: tuple[BasketItemQuery, ...]
    savings_vs_worst_uzs: Decimal
    savings_pct: float
    max_eta_hours: int
    composite_score: float = 0.0


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Top-level container returned to caller with variants and metadata."""

    variants: tuple[QuoteVariant, ...]
    deduplicated_variants: tuple[QuoteVariant, ...]
    total_candidate_shops: int
    total_offers_evaluated: int
    solve_duration_ms: float
