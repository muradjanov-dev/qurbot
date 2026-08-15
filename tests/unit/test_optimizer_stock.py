"""Stock availability rules in the optimizer.

Two rules, and the second one exists so a basket is never left empty:

1. A shop that cannot supply the requested amount is not offered at all.
2. If no shop can, the shop holding the most of that product is offered anyway
   -- a partial fill the customer can see beats showing them nothing.
"""

from decimal import Decimal

from app.domain.optimizer import BasketItemQuery, BasketOptimizer, DeliveryTier, ShopOffer


def _item(qty: str, unit: str = "qop") -> BasketItemQuery:
    return BasketItemQuery(
        line_no=1,
        canonical_id=1,
        name_uz="Sement M400",
        needed_qty=Decimal(qty),
        unit_code=unit,
    )


def _offer(
    offer_id: int,
    shop_id: int,
    price: str,
    stock_qty: str | None,
    pack_size: str = "1",
    pack_unit: str = "qop",
) -> ShopOffer:
    return ShopOffer(
        offer_id=offer_id,
        shop_id=shop_id,
        shop_name=f"Shop {shop_id}",
        canonical_id=1,
        price_uzs=Decimal(price),
        pack_size=Decimal(pack_size),
        pack_unit=pack_unit,
        in_stock=True,
        stock_status="in_stock",
        staleness_state="fresh",
        tier="standard",
        brand_name=None,
        trust_score=1.0,
        eta_hours=24,
        is_active=True,
        district_id=1,
        stock_qty=Decimal(stock_qty) if stock_qty is not None else None,
    )


def _rules(*shop_ids: int) -> dict[int, DeliveryTier]:
    return {
        sid: DeliveryTier(
            shop_id=sid,
            district_id=1,
            base_fee_uzs=Decimal("0"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        )
        for sid in shop_ids
    }


def _chosen_shop_ids(result: object) -> set[int]:
    variant = result.deduplicated_variants[0]  # type: ignore[attr-defined]
    return {group.shop_id for group in variant.shop_groups}


def test_shop_without_enough_stock_is_excluded() -> None:
    """The cheaper shop only has 3 of the 10 needed, so it must not be offered."""
    optimizer = BasketOptimizer(
        basket_items=[_item("10")],
        offers=[
            _offer(1, 1, price="50000", stock_qty="3"),
            _offer(2, 2, price="60000", stock_qty="500"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {2}


def test_shop_with_exactly_enough_stock_qualifies() -> None:
    optimizer = BasketOptimizer(
        basket_items=[_item("10")],
        offers=[
            _offer(1, 1, price="50000", stock_qty="10"),
            _offer(2, 2, price="60000", stock_qty="500"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {1}, "exactly enough is enough"


def test_unknown_stock_is_treated_as_available() -> None:
    """NULL stock means the shop does not track it -- not that it has none."""
    optimizer = BasketOptimizer(
        basket_items=[_item("10")],
        offers=[
            _offer(1, 1, price="50000", stock_qty=None),
            _offer(2, 2, price="60000", stock_qty="500"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {1}


def test_falls_back_to_the_largest_holding_when_nobody_has_enough() -> None:
    """Nobody can fill 100; the shop with 40 is offered rather than nothing."""
    optimizer = BasketOptimizer(
        basket_items=[_item("100")],
        offers=[
            _offer(1, 1, price="50000", stock_qty="5"),
            _offer(2, 2, price="60000", stock_qty="40"),
            _offer(3, 3, price="45000", stock_qty="12"),
        ],
        delivery_rules=_rules(1, 2, 3),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {2}, "largest holding wins even though it is dearest"


def test_fallback_prefers_cheaper_among_equal_holdings() -> None:
    optimizer = BasketOptimizer(
        basket_items=[_item("100")],
        offers=[
            _offer(1, 1, price="70000", stock_qty="40"),
            _offer(2, 2, price="50000", stock_qty="40"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {2}


def test_zero_stock_shop_never_wins_over_a_stocked_one() -> None:
    optimizer = BasketOptimizer(
        basket_items=[_item("10")],
        offers=[
            _offer(1, 1, price="10000", stock_qty="0"),
            _offer(2, 2, price="90000", stock_qty="10"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {2}


def test_pack_size_is_respected_when_counting_stock() -> None:
    """Needing 100 kg from 50 kg bags is 2 bags -- a shop with 2 bags qualifies."""
    optimizer = BasketOptimizer(
        basket_items=[_item("100", unit="kg")],
        offers=[
            _offer(1, 1, price="52000", stock_qty="2", pack_size="50", pack_unit="kg"),
            _offer(2, 2, price="60000", stock_qty="99", pack_size="50", pack_unit="kg"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {1}


def test_insufficient_packs_are_excluded_after_pack_rounding() -> None:
    """Needing 100 kg is 2 bags; a shop with 1 bag cannot fill it."""
    optimizer = BasketOptimizer(
        basket_items=[_item("100", unit="kg")],
        offers=[
            _offer(1, 1, price="52000", stock_qty="1", pack_size="50", pack_unit="kg"),
            _offer(2, 2, price="60000", stock_qty="99", pack_size="50", pack_unit="kg"),
        ],
        delivery_rules=_rules(1, 2),
    )
    result = optimizer.solve()
    assert _chosen_shop_ids(result) == {2}


def test_stock_filtering_is_deterministic() -> None:
    offers = [
        _offer(1, 1, price="50000", stock_qty="4"),
        _offer(2, 2, price="50000", stock_qty="4"),
        _offer(3, 3, price="50000", stock_qty="4"),
    ]
    first = BasketOptimizer([_item("100")], list(offers), _rules(1, 2, 3)).solve()
    second = BasketOptimizer([_item("100")], list(reversed(offers)), _rules(1, 2, 3)).solve()
    assert _chosen_shop_ids(first) == _chosen_shop_ids(second)
