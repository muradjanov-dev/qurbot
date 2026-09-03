import logging

from app.core.metrics import quote_latency_seconds
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.optimizer import (
    BasketItemQuery,
    BasketOptimizer,
    DeliveryTier,
    OptimizationResult,
    ShopOffer,
)

logger = logging.getLogger(__name__)


class QuoteService:
    """Service layer orchestrating database loading and pure in-memory basket cost optimization."""

    def __init__(
        self,
        shop_repo: ShopRepository,
        catalog_repo: CatalogRepository,
    ) -> None:
        self.shop_repo = shop_repo
        self.catalog_repo = catalog_repo

    async def optimize_basket(
        self,
        basket_items: list[BasketItemQuery],
        district_id: int | None = None,
        customer_lat: float | None = None,
        customer_lon: float | None = None,
    ) -> OptimizationResult:
        if not basket_items:
            empty_optimizer = BasketOptimizer([], [], {})
            return empty_optimizer.solve()

        # If coordinates not provided, try to lookup district centroid
        if (customer_lat is None or customer_lon is None) and district_id is not None:
            district = await self.shop_repo.get_district(district_id)
            if district and district.centroid_lat and district.centroid_lng:
                customer_lat = float(district.centroid_lat)
                customer_lon = float(district.centroid_lng)

        canonical_ids = list({item.canonical_id for item in basket_items})

        # 1. Single database query for all candidate offers
        db_offers = await self.shop_repo.get_active_offers_for_canonicals(canonical_ids)
        if not db_offers:
            empty_optimizer = BasketOptimizer(basket_items, [], {})
            return empty_optimizer.solve()

        # 2. Single database query for all candidate shop delivery rules
        shop_ids = list({o.shop_id for o in db_offers})
        db_rules = await self.shop_repo.get_delivery_rules_for_shops(shop_ids, district_id)

        # 3. Convert DB models to pure domain dataclasses
        domain_offers: list[ShopOffer] = []
        for o in db_offers:
            rule = db_rules.get(o.shop_id)
            eta = rule.eta_hours if rule else 24
            tier = (
                o.canonical_product.tier
                if o.canonical_product and o.canonical_product.tier
                else "standard"
            )
            brand = o.canonical_product.brand if o.canonical_product else None
            lat = float(o.shop.lat) if o.shop and o.shop.lat is not None else None
            lon = float(o.shop.lng) if o.shop and o.shop.lng is not None else None
            trust = float(o.shop.trust_score) if o.shop and o.shop.trust_score is not None else 1.0

            domain_offers.append(
                ShopOffer(
                    offer_id=o.id,
                    shop_id=o.shop_id,
                    shop_name=o.shop.name if o.shop else f"Shop #{o.shop_id}",
                    canonical_id=o.canonical_id or 0,
                    price_uzs=o.price_per_pack,
                    pack_size=o.pack_size,
                    pack_unit=o.pack_unit_code or "dona",
                    in_stock=(o.stock_status in ("in_stock", "low")),
                    stock_status=o.stock_status,
                    staleness_state=o.staleness_state,
                    tier=tier,
                    brand_name=brand,
                    trust_score=trust,
                    eta_hours=eta,
                    is_active=o.is_active,
                    district_id=o.shop.district_id if o.shop else None,
                    lat=lat,
                    lon=lon,
                    stock_qty=o.stock_qty,
                    # Loaded with the offer (selectin), so volume prices cost
                    # one extra query for the whole basket rather than one per
                    # offer on the hot quote path.
                    price_tiers=tuple(
                        (tier.min_qty, tier.price_per_pack) for tier in (o.price_tiers or [])
                    ),
                )
            )

        domain_rules: dict[int, DeliveryTier] = {}
        for s_id, r in db_rules.items():
            domain_rules[s_id] = DeliveryTier(
                shop_id=r.shop_id,
                district_id=r.district_id or 0,
                base_fee_uzs=r.fee,
                free_above_uzs=r.free_above,
                min_order_uzs=r.min_order,
                eta_hours=r.eta_hours,
            )

        # 4. Run pure in-memory optimizer
        optimizer = BasketOptimizer(
            basket_items=basket_items,
            offers=domain_offers,
            delivery_rules=domain_rules,
            customer_lat=customer_lat,
            customer_lon=customer_lon,
        )

        result = optimizer.solve()
        quote_latency_seconds.observe(result.solve_duration_ms / 1000)
        logger.info(
            "Basket optimization completed in %.2f ms (evaluated %d offers across %d shops)",
            result.solve_duration_ms,
            result.total_offers_evaluated,
            result.total_candidate_shops,
        )
        return result
