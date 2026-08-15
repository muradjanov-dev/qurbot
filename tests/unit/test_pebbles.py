from decimal import Decimal

from app.domain.rewards import pebbles_for_order

RATE = Decimal("0.001")  # 0.1%


def test_award_is_one_tenth_of_a_percent() -> None:
    assert pebbles_for_order(Decimal("1000000"), RATE) == 1000
    assert pebbles_for_order(Decimal("638200"), RATE) == 638


def test_award_rounds_down() -> None:
    """638.2 pebbles is 638 -- never round up into currency nobody earned."""
    assert pebbles_for_order(Decimal("638999"), RATE) == 638
    assert pebbles_for_order(Decimal("999"), RATE) == 0


def test_non_positive_totals_earn_nothing() -> None:
    assert pebbles_for_order(Decimal("0"), RATE) == 0
    assert pebbles_for_order(Decimal("-5000"), RATE) == 0


def test_zero_rate_disables_awards() -> None:
    assert pebbles_for_order(Decimal("1000000"), Decimal("0")) == 0


def test_rate_is_configurable() -> None:
    assert pebbles_for_order(Decimal("100000"), Decimal("0.01")) == 1000
