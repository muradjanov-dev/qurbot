"""Offer availability ignores numeric quantities and honors explicit status."""

from decimal import Decimal

from app.domain.optimizer import BasketItemQuery, BasketOptimizer, DeliveryTier, ShopOffer


def _item() -> BasketItemQuery:
    return BasketItemQuery(
        line_no=1,
        canonical_id=1,
        name_uz="Sement M400",
        needed_qty=Decimal("100"),
        unit_code="qop",
    )


def _offer(
    offer_id: int, shop_id: int, price: str, qty: str | None, status: str = "in_stock"
) -> ShopOffer:
    return ShopOffer(
        offer_id=offer_id,
        shop_id=shop_id,
        shop_name=f"Shop {shop_id}",
        canonical_id=1,
        price_uzs=Decimal(price),
        pack_size=Decimal("1"),
        pack_unit="qop",
        in_stock=status in {"in_stock", "low"},
        stock_status=status,
        staleness_state="fresh",
        tier="standard",
        brand_name=None,
        trust_score=1.0,
        eta_hours=24,
        is_active=True,
        district_id=1,
        stock_qty=Decimal(qty) if qty is not None else None,
    )


def _rules() -> dict[int, DeliveryTier]:
    return {
        sid: DeliveryTier(
            shop_id=sid,
            district_id=1,
            base_fee_uzs=Decimal("0"),
            free_above_uzs=None,
            min_order_uzs=Decimal("0"),
            eta_hours=24,
        )
        for sid in (1, 2, 3)
    }


def _chosen_shop_ids(result: object) -> set[int]:
    variant = result.deduplicated_variants[0]  # type: ignore[attr-defined]
    return {group.shop_id for group in variant.shop_groups}


def test_low_numeric_stock_does_not_exclude_offer() -> None:
    """Quantities no longer constrain a quote; availability is status based."""
    optimizer = BasketOptimizer(
        [_item()],
        [_offer(1, 1, "50000", "0"), _offer(2, 2, "60000", "1")],
        _rules(),
    )
    assert _chosen_shop_ids(optimizer.solve()) == {1}


def test_unknown_and_legacy_numeric_stock_are_equally_unlimited() -> None:
    optimizer = BasketOptimizer(
        [_item()],
        [_offer(1, 1, "50000", None), _offer(2, 2, "60000", "1")],
        _rules(),
    )
    assert _chosen_shop_ids(optimizer.solve()) == {1}


def test_out_offer_remains_unavailable() -> None:
    optimizer = BasketOptimizer(
        [_item()],
        [_offer(1, 1, "10000", "500", "out"), _offer(2, 2, "60000", "1")],
        _rules(),
    )
    assert _chosen_shop_ids(optimizer.solve()) == {2}


def test_stock_agnostic_selection_is_deterministic() -> None:
    offers = [_offer(1, 1, "50000", "4"), _offer(2, 2, "50000", "0")]
    a = BasketOptimizer([_item()], offers, _rules()).solve()
    b = BasketOptimizer([_item()], list(reversed(offers)), _rules()).solve()
    assert _chosen_shop_ids(a) == _chosen_shop_ids(b)
