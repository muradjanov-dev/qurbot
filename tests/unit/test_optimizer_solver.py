from decimal import Decimal

from app.domain.optimizer.models import (
    BasketItemQuery,
    DeliveryTier,
    OptimizationStrategy,
    ShopOffer,
)
from app.domain.optimizer.solver import BasketOptimizer


def test_optimizer_avoids_unnecessary_delivery_split() -> None:
    # Item 1: Sement 10 qop (500 kg)
    # Item 2: Gisht 500 dona
    basket = [
        BasketItemQuery(
            line_no=1,
            canonical_id=1,
            name_uz="Sement M400",
            needed_qty=Decimal("10"),
            unit_code="qop",
        ),
        BasketItemQuery(
            line_no=2,
            canonical_id=2,
            name_uz="G'isht M100",
            needed_qty=Decimal("500"),
            unit_code="dona",
        ),
    ]

    # Shop A has slightly cheaper cement (50,000 vs 52,000) and expensive bricks (1500 vs 1300)
    # Delivery fee: 40,000 UZS each
    offers = [
        ShopOffer(
            offer_id=101,
            shop_id=1,
            shop_name="Shop A",
            canonical_id=1,
            price_uzs=Decimal("50000"),
            pack_size=Decimal("1"),
            pack_unit="qop",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name=None,
            trust_score=1.0,
            eta_hours=24,
            is_active=True,
        ),
        ShopOffer(
            offer_id=102,
            shop_id=1,
            shop_name="Shop A",
            canonical_id=2,
            price_uzs=Decimal("1500"),
            pack_size=Decimal("1"),
            pack_unit="dona",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name=None,
            trust_score=1.0,
            eta_hours=24,
            is_active=True,
        ),
        # Shop B has slightly more expensive cement (51,000) and cheaper bricks (1300)
        ShopOffer(
            offer_id=201,
            shop_id=2,
            shop_name="Shop B",
            canonical_id=1,
            price_uzs=Decimal("51000"),
            pack_size=Decimal("1"),
            pack_unit="qop",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name=None,
            trust_score=1.0,
            eta_hours=24,
            is_active=True,
        ),
        ShopOffer(
            offer_id=202,
            shop_id=2,
            shop_name="Shop B",
            canonical_id=2,
            price_uzs=Decimal("1300"),
            pack_size=Decimal("1"),
            pack_unit="dona",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name=None,
            trust_score=1.0,
            eta_hours=24,
            is_active=True,
        ),
    ]

    delivery_rules = {
        1: DeliveryTier(
            shop_id=1,
            district_id=1,
            base_fee_uzs=Decimal("40000"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        ),
        2: DeliveryTier(
            shop_id=2,
            district_id=1,
            base_fee_uzs=Decimal("40000"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        ),
    }

    # If split:
    # Shop A cement (500,000) + delivery (40,000) = 540,000
    # Shop B bricks (650,000) + delivery (40,000) = 690,000
    # Split total = 1,230,000
    # If all at Shop B:
    # Shop B cement (510,000) + bricks (650,000) + 1 delivery (40,000) = 1,200,000 (Saves 30k!)
    optimizer = BasketOptimizer(basket, offers, delivery_rules)
    result = optimizer.solve()

    cheapest_var = next(
        v for v in result.variants if OptimizationStrategy.CHEAPEST_TOTAL in v.strategy_labels
    )
    assert len(cheapest_var.shop_groups) == 1
    assert cheapest_var.shop_groups[0].shop_id == 2
    assert cheapest_var.grand_total_uzs == Decimal("1200000")


def test_optimizer_determinism() -> None:
    basket = [
        BasketItemQuery(
            line_no=1,
            canonical_id=1,
            name_uz="Sement M400",
            needed_qty=Decimal("10"),
            unit_code="qop",
        ),
        BasketItemQuery(
            line_no=2,
            canonical_id=2,
            name_uz="G'isht M100",
            needed_qty=Decimal("500"),
            unit_code="dona",
        ),
    ]
    offers = [
        ShopOffer(
            offer_id=1,
            shop_id=1,
            shop_name="Shop 1",
            canonical_id=1,
            price_uzs=Decimal("50000"),
            pack_size=Decimal("1"),
            pack_unit="qop",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name=None,
            trust_score=0.9,
            eta_hours=24,
            is_active=True,
        ),
        ShopOffer(
            offer_id=2,
            shop_id=2,
            shop_name="Shop 2",
            canonical_id=2,
            price_uzs=Decimal("1350"),
            pack_size=Decimal("1"),
            pack_unit="dona",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name=None,
            trust_score=0.95,
            eta_hours=12,
            is_active=True,
        ),
    ]
    rules = {
        1: DeliveryTier(
            shop_id=1,
            district_id=1,
            base_fee_uzs=Decimal("30000"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        ),
        2: DeliveryTier(
            shop_id=2,
            district_id=1,
            base_fee_uzs=Decimal("35000"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=12,
        ),
    }

    res1 = BasketOptimizer(basket, offers, rules).solve()
    res2 = BasketOptimizer(basket, offers, rules).solve()

    assert len(res1.variants) == len(res2.variants)
    for v1, v2 in zip(res1.variants, res2.variants, strict=True):
        assert v1.strategy_labels == v2.strategy_labels
        assert v1.grand_total_uzs == v2.grand_total_uzs
        assert v1.items_total_uzs == v2.items_total_uzs
        assert v1.delivery_total_uzs == v2.delivery_total_uzs
        assert len(v1.shop_groups) == len(v2.shop_groups)


def test_optimizer_pack_rounding_in_line_assignment() -> None:
    # 7 kg needed with 25 kg bag pack size -> 1 pack (25 kg billed)
    basket = [
        BasketItemQuery(
            line_no=1,
            canonical_id=10,
            name_uz="Plitka Yelimi",
            needed_qty=Decimal("7"),
            unit_code="kg",
        ),
    ]
    offers = [
        ShopOffer(
            offer_id=55,
            shop_id=5,
            shop_name="Kley Shop",
            canonical_id=10,
            price_uzs=Decimal("45000"),
            pack_size=Decimal("25"),
            pack_unit="kg",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="standard",
            brand_name="Ceresit",
            trust_score=1.0,
            eta_hours=24,
            is_active=True,
        ),
    ]
    rules = {
        5: DeliveryTier(
            shop_id=5,
            district_id=1,
            base_fee_uzs=Decimal("20000"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        ),
    }

    res = BasketOptimizer(basket, offers, rules).solve()
    var = res.variants[0]
    line = var.shop_groups[0].lines[0]
    assert line.packs_needed == 1
    assert line.billed_qty == Decimal("25")
    assert line.overage_qty == Decimal("18")
    assert line.line_cost_uzs == Decimal("45000")


def test_optimizer_deduplication() -> None:
    basket = [
        BasketItemQuery(
            line_no=1, canonical_id=1, name_uz="Item 1", needed_qty=Decimal("1"), unit_code="dona"
        ),
    ]
    offers = [
        ShopOffer(
            offer_id=1,
            shop_id=1,
            shop_name="Only Shop",
            canonical_id=1,
            price_uzs=Decimal("10000"),
            pack_size=Decimal("1"),
            pack_unit="dona",
            in_stock=True,
            stock_status="in_stock",
            staleness_state="fresh",
            tier="premium",
            brand_name="Brand",
            trust_score=1.0,
            eta_hours=12,
            is_active=True,
        ),
    ]
    rules = {
        1: DeliveryTier(
            shop_id=1,
            district_id=1,
            base_fee_uzs=Decimal("10000"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=12,
        ),
    }

    res = BasketOptimizer(basket, offers, rules).solve()
    # All 5 strategies pick the only shop, so deduplicated should collapse to 1 card
    assert len(res.deduplicated_variants) == 1
    labels = res.deduplicated_variants[0].strategy_labels
    assert OptimizationStrategy.CHEAPEST_TOTAL in labels
    assert OptimizationStrategy.SINGLE_SHOP in labels
    assert OptimizationStrategy.FASTEST in labels
    assert OptimizationStrategy.PREMIUM in labels
    assert OptimizationStrategy.BALANCED in labels
