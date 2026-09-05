"""An offer nobody can cost must not take the quote down with it.

Straight off production: a customer ordered in kilos from a catalogue that
sells that family by the box, and the whole basket came back as an error --
including the lines that priced perfectly well. Pricing happens inside a
`min()` over candidate offers, so a raise there escapes the solver entirely.
"""

from decimal import Decimal

import pytest

from app.domain.optimizer import BasketItemQuery, BasketOptimizer, DeliveryTier, ShopOffer
from app.domain.pricing.units import can_price_line


def _item(line_no: int, canonical_id: int, qty: str, unit: str) -> BasketItemQuery:
    return BasketItemQuery(
        line_no=line_no,
        canonical_id=canonical_id,
        name_uz=f"Mahsulot {canonical_id}",
        needed_qty=Decimal(qty),
        unit_code=unit,
    )


def _offer(offer_id: int, canonical_id: int, pack_unit: str, price: str = "100000") -> ShopOffer:
    return ShopOffer(
        offer_id=offer_id,
        shop_id=1,
        shop_name="QurBot",
        canonical_id=canonical_id,
        price_uzs=Decimal(price),
        pack_size=Decimal("1"),
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
    )


_RULES = {
    1: DeliveryTier(
        shop_id=1,
        district_id=1,
        base_fee_uzs=Decimal("0"),
        free_above_uzs=None,
        min_order_uzs=Decimal("0"),
        eta_hours=24,
    )
}


@pytest.mark.parametrize(
    ("required", "pack", "priceable"),
    [
        # Same dimension: ordinary pricing.
        ("kg", "kg", True),
        ("tonna", "kg", True),
        ("dona", "quti", True),
        # A bare package count against anything: one package is one pack.
        ("quti", "kg", True),
        ("pachka", "kg", True),
        ("qop", "m2", True),
        # No conversion exists: nobody recorded what a box of screws weighs.
        ("kg", "quti", False),
        ("kg", "pachka", False),
        ("m2", "kg", False),
        # A unit nobody recognises -- a shop is free to type anything.
        ("kg", "banka", False),
        ("banka", "kg", False),
    ],
)
def test_which_lines_can_be_costed(required: str, pack: str, priceable: bool) -> None:
    assert can_price_line(required, pack) is priceable


def test_the_pack_units_the_catalogue_uses_are_all_known() -> None:
    """`pachka` reached the seed and the parser before it reached pricing."""
    for unit in ("dona", "kg", "quti", "pachka", "qop", "rulon", "m2", "m3", "metr"):
        assert can_price_line(unit, unit) is True


def test_one_unpriceable_line_does_not_take_the_basket_with_it() -> None:
    """The kilo line cannot be costed; the box line still must be."""
    optimizer = BasketOptimizer(
        basket_items=[_item(1, 10, "5", "kg"), _item(2, 20, "3", "quti")],
        offers=[_offer(1, 10, "quti"), _offer(2, 20, "quti")],
        delivery_rules=_RULES,
    )

    result = optimizer.solve()

    assert result.variants
    variant = result.variants[0]
    quoted = [a.line_no for group in variant.shop_groups for a in group.lines]
    assert quoted == [2]
    assert [m.line_no for m in variant.missing_lines] == [1]


def test_a_basket_of_only_unpriceable_lines_answers_instead_of_raising() -> None:
    optimizer = BasketOptimizer(
        basket_items=[_item(1, 10, "5", "kg")],
        offers=[_offer(1, 10, "quti")],
        delivery_rules=_RULES,
    )

    result = optimizer.solve()

    assert result.variants
    variant = result.variants[0]
    assert variant.shop_groups == ()
    assert [m.line_no for m in variant.missing_lines] == [1]


def test_a_shop_typing_a_unit_nobody_knows_costs_only_that_offer() -> None:
    """One bad row in an Excel upload used to fail every quote it appeared in."""
    optimizer = BasketOptimizer(
        basket_items=[_item(1, 10, "5", "kg")],
        offers=[_offer(1, 10, "banka", price="90000"), _offer(2, 10, "kg", price="100000")],
        delivery_rules=_RULES,
    )

    result = optimizer.solve()

    quoted = [a.offer_id for group in result.variants[0].shop_groups for a in group.lines]
    assert quoted == [2], "the sane offer is quoted, not the junk one"
