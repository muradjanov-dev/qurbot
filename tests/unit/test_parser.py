from decimal import Decimal

import pytest

from app.domain.parsing.parser import is_qty_orderable, parse_basket_lines, split_message_to_lines


def test_split_message_lines() -> None:
    # 1. Comma separated with decimal protection (12,5 should not split)
    msg1 = "500 dona g'isht, 10 qop cement m400, 3 quti plitka 30x30"
    lines1 = split_message_to_lines(msg1)
    assert len(lines1) == 3
    assert "500 dona g'isht" in lines1[0]
    assert "10 qop cement m400" in lines1[1]
    assert "3 quti plitka 30x30" in lines1[2]

    # Decimal comma protection
    msg2 = "Gipsokarton 12,5mm 40 list, 1,5 kub shag'al"
    lines2 = split_message_to_lines(msg2)
    assert len(lines2) == 2
    assert "12,5mm" in lines2[0] or "12.5mm" in lines2[0]
    assert "1,5 kub" in lines2[1] or "1.5 kub" in lines2[1]

    # Newlines and bullet points
    msg3 = """
    • цемент м400 - 20 қоп
    • армaтура 12мм 500 кг
    - 5 rulon ruberoid
    1. 2t qum
    2) 1.5 kub shag'al
    """
    lines3 = split_message_to_lines(msg3)
    assert len(lines3) == 5


@pytest.mark.parametrize(
    ("raw_line", "expected_name", "expected_qty", "expected_unit"),
    [
        ("500 dona g'isht", "g'isht", Decimal("500"), "dona"),
        ("10 qop cement m400", "cement m400", Decimal("10"), "qop"),
        ("3 quti plitka 30x30", "plitka 30x30", Decimal("3"), "quti"),
        ("цемент м400 - 20 қоп", "sement m400", Decimal("20"), "qop"),
        ("армaтура 12мм 500 кг", "armatura 12mm", Decimal("500"), "kg"),
        ("5 rulon ruberoid", "ruberoid", Decimal("5"), "rulon"),
        ("Gipsokarton 12.5mm 40 list", "gipsokarton 12.5mm", Decimal("40"), "dona"),
        # Normalization rewrites the Russian trade word and its colour into
        # the catalog's own wording, which is what the matcher searches.
        ("kraska belaya 3 vedra 10l", "bo'yoq oq", Decimal("30"), "litr"),
        ("2t qum", "qum", Decimal("2"), "tonna"),
        ("1.5 kub shag'al", "shag'al", Decimal("1.5"), "m3"),
        ("100 metr armatura 14mm", "armatura 14mm", Decimal("100"), "metr"),
        ("25 kg plitka yelimi", "plitka yelimi", Decimal("25"), "kg"),
        ("rotband 15 qop", "rotband", Decimal("15"), "qop"),
    ],
)
def test_parse_single_line_fixtures(
    raw_line: str,
    expected_name: str,
    expected_qty: Decimal,
    expected_unit: str,
) -> None:
    parsed = parse_basket_lines(raw_line)
    assert len(parsed) == 1
    p = parsed[0]
    assert p.qty == expected_qty
    assert p.unit_code == expected_unit
    assert expected_name in p.parsed_name


def test_parse_full_basket_text() -> None:
    basket_text = """
    500 dona g'isht, 10 qop cement m400, 3 quti plitka 30x30
    цемент м400 - 20 қоп
    армaтура 12мм 500 кг
    5 rulon ruberoid
    Gipsokarton 12.5mm 40 list
    kraska belaya 3 vedra 10l
    2t qum, 1.5 kub shag'al
    """
    lines = parse_basket_lines(basket_text)
    assert len(lines) == 10
    assert all(line.qty > Decimal("0") for line in lines)
    assert all(line.unit_code is not None for line in lines)


def test_parse_range_quantity() -> None:
    # Range: 10-15 qop cement -> takes upper bound (15) and flags needs_review
    parsed = parse_basket_lines("10-15 qop sement m400")
    assert len(parsed) == 1
    assert parsed[0].qty == Decimal("15")
    assert parsed[0].needs_review is True


def test_parse_multiplier() -> None:
    # 5 x 10 qop sement -> 50 qop
    parsed = parse_basket_lines("5 x 10 qop sement m400")
    assert len(parsed) == 1
    assert parsed[0].qty == Decimal("50")
    assert parsed[0].unit_code == "qop"


def test_qty_within_bounds_accepts_ordinary_quantities() -> None:
    assert is_qty_orderable(Decimal("1"))
    assert is_qty_orderable(Decimal("500"))
    assert is_qty_orderable(Decimal("0.5"))
    assert is_qty_orderable(Decimal("1000000"))


def test_qty_within_bounds_rejects_zero_and_negative() -> None:
    """Nothing below 1 can be ordered, so these are input errors, not orders."""
    assert not is_qty_orderable(Decimal("0"))
    assert not is_qty_orderable(Decimal("-5"))
    assert not is_qty_orderable(Decimal("-0.01"))


def test_qty_within_bounds_rejects_absurd_quantities() -> None:
    """A 12-digit quantity is a typo; pricing it produces a meaningless total."""
    assert not is_qty_orderable(Decimal("1000001"))
    assert not is_qty_orderable(Decimal("999999999999"))


def test_qty_bound_is_configurable() -> None:
    assert is_qty_orderable(Decimal("50"), max_qty=Decimal("100"))
    assert not is_qty_orderable(Decimal("150"), max_qty=Decimal("100"))


def test_leading_dash_with_space_is_a_bullet_not_a_negative() -> None:
    """List bullets are common ("- 10 qop sement") and must keep their meaning."""
    lines = parse_basket_lines("- 10 qop sement\n- 500 dona gisht")
    assert [line.qty for line in lines] == [Decimal("10"), Decimal("500")]


def test_dash_attached_to_a_number_stays_negative() -> None:
    """ "-5 dona" is a negative quantity, not a bullet.

    It used to be silently read as 5, so a customer who typed -5 got an order
    for 5 rather than an error.
    """
    lines = parse_basket_lines("-5 dona sement")
    assert len(lines) == 1
    assert lines[0].qty == Decimal("-5")
    assert not is_qty_orderable(lines[0].qty)


def test_conjunction_splits_only_when_both_halves_are_quantified() -> None:
    """ "va" separates two orders, but it also lives inside ordinary names."""
    two_orders = parse_basket_lines("500 dona kirpich va 2 tonna pesok")
    assert len(two_orders) == 2
    assert two_orders[0].qty == Decimal("500")
    assert two_orders[1].qty == Decimal("2")
    assert two_orders[1].unit_code == "tonna"

    # No quantities on either side: one product phrase, left intact.
    assert len(parse_basket_lines("eshik va deraza")) == 1

    # Only one side is quantified -- still a single line.
    assert len(parse_basket_lines("sement va 10 qop qum")) == 1

    # Both halves mention a number, but neither is a parseable order line:
    # left whole, so the message can still reach the LLM parser intact.
    prose = parse_basket_lines("bizga faneradan 10ta va osbdan 5ta kerak edi")
    assert len(prose) == 1

    # The word must stand alone; "vagonka" is not a conjunction.
    single = parse_basket_lines("10 dona vagonka")
    assert len(single) == 1
    assert single[0].qty == Decimal("10")
