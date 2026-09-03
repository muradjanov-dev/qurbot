"""A big order is billed at the wholesale price, not the retail one.

The tier lives on the offer, but it only matters if the optimizer applies it
when it costs a line -- and it has to apply it after working out how many packs
are needed, since that is what the threshold is measured against.
"""

from decimal import Decimal

from app.domain.optimizer.models import BasketItemQuery, DeliveryTier, ShopOffer
from app.domain.optimizer.solver import BasketOptimizer

RETAIL = Decimal("120600")
WHOLESALE = Decimal("118200")
FROM_PACKS = Decimal("200")


def _offer(with_tier: bool) -> ShopOffer:
    return ShopOffer(
        offer_id=1,
        shop_id=1,
        shop_name="QurBot",
        canonical_id=7,
        price_uzs=RETAIL,
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
        price_tiers=((FROM_PACKS, WHOLESALE),) if with_tier else (),
    )


def _basket(qty: str) -> list[BasketItemQuery]:
    return [
        BasketItemQuery(
            line_no=1,
            canonical_id=7,
            name_uz="Fanera 4 mm",
            needed_qty=Decimal(qty),
            unit_code="dona",
        )
    ]


def _total(qty: str, *, with_tier: bool) -> Decimal:
    rules = {
        1: DeliveryTier(
            shop_id=1,
            district_id=0,
            base_fee_uzs=Decimal("0"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        )
    }
    result = BasketOptimizer(_basket(qty), [_offer(with_tier)], rules).solve()
    return result.deduplicated_variants[0].items_total_uzs


def test_below_the_threshold_the_retail_price_stands() -> None:
    assert _total("50", with_tier=True) == RETAIL * 50


def test_at_the_threshold_the_whole_order_is_wholesale() -> None:
    """ "From 200" prices all two hundred, which is how the trade quotes it."""
    assert _total("200", with_tier=True) == WHOLESALE * 200


def test_the_tier_is_what_makes_the_difference() -> None:
    with_tier = _total("300", with_tier=True)
    without = _total("300", with_tier=False)
    assert with_tier < without
    assert without - with_tier == (RETAIL - WHOLESALE) * 300
