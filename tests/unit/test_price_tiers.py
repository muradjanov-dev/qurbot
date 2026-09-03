"""Wholesale pricing: a cheaper per-pack price from a quantity upward.

The trade quotes it as two numbers and a threshold -- "10.2$ a sheet, 10$ from
200 sheets". Without it, a customer ordering a lorry-load is quoted the retail
price, which is wrong in the direction that loses the order to a phone call.
"""

from decimal import Decimal

from app.domain.optimizer.models import ShopOffer

RETAIL = Decimal("120600")  # 10.2$ at 11 820.48
WHOLESALE = Decimal("118200")  # 10$


def _offer(tiers: tuple[tuple[Decimal, Decimal], ...] = ()) -> ShopOffer:
    return ShopOffer(
        offer_id=1,
        shop_id=1,
        shop_name="QurBot",
        canonical_id=1,
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
        price_tiers=tiers,
    )


def test_a_small_order_pays_the_retail_price() -> None:
    offer = _offer(((Decimal("200"), WHOLESALE),))
    assert offer.price_for_packs(Decimal("50")) == RETAIL


def test_the_threshold_itself_already_counts() -> None:
    """ "from 200 sheets" includes the two hundredth."""
    offer = _offer(((Decimal("200"), WHOLESALE),))
    assert offer.price_for_packs(Decimal("200")) == WHOLESALE


def test_a_bigger_order_keeps_the_wholesale_price() -> None:
    offer = _offer(((Decimal("200"), WHOLESALE),))
    assert offer.price_for_packs(Decimal("5000")) == WHOLESALE


def test_the_deepest_applicable_tier_wins() -> None:
    """Several thresholds: the customer gets the best one they have reached."""
    offer = _offer(
        (
            (Decimal("100"), Decimal("119000")),
            (Decimal("200"), WHOLESALE),
            (Decimal("500"), Decimal("115000")),
        )
    )
    assert offer.price_for_packs(Decimal("99")) == RETAIL
    assert offer.price_for_packs(Decimal("100")) == Decimal("119000")
    assert offer.price_for_packs(Decimal("300")) == WHOLESALE
    assert offer.price_for_packs(Decimal("500")) == Decimal("115000")


def test_tiers_out_of_order_are_still_read_correctly() -> None:
    """Rows arrive in whatever order the database returns them."""
    offer = _offer(
        (
            (Decimal("500"), Decimal("115000")),
            (Decimal("100"), Decimal("119000")),
        )
    )
    assert offer.price_for_packs(Decimal("600")) == Decimal("115000")


def test_a_tier_above_the_retail_price_never_costs_more() -> None:
    """A mistyped tier must not make a bigger order more expensive."""
    offer = _offer(((Decimal("10"), Decimal("999999")),))
    assert offer.price_for_packs(Decimal("100")) == RETAIL


def test_an_offer_without_tiers_is_unchanged() -> None:
    assert _offer().price_for_packs(Decimal("10000")) == RETAIL
