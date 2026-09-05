"""Notation taken straight from the unmatched queue.

Every line here was typed by a customer and failed. They are not edge cases --
"03m" and a size followed by a dashed quantity account for a third of
everything the matcher could not read.
"""

from decimal import Decimal

import pytest

from app.domain.normalize.text import normalize_text
from app.domain.parsing.parser import parse_basket_lines


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # A leading zero before "m" is the price list's way of writing a
        # thickness: nobody orders three metres of plywood.
        ("fanera 03m", "fanera 3mm"),
        ("fanera 04m", "fanera 4mm"),
        ("fanera 08m", "fanera 8mm"),
        # Without the leading zero it stays a length, because "3 m" of cable or
        # skirting is an ordinary thing to ask for.
        ("kabel 3m", "kabel 3m"),
    ],
)
def test_zero_padded_millimetres(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_a_size_is_not_a_numeric_range() -> None:
    """ "1.5x1.5 - 15 ta" is a size and a quantity, not "from 1.5 to 15".

    Read as a range it produced "1500x1150" -- a sheet that does not exist --
    and swallowed the quantity with it.
    """
    lines = parse_basket_lines("Faner 12mm 1.5x1.5 - 15 ta")

    assert len(lines) == 1
    line = lines[0]
    assert line.qty == Decimal("15")
    assert "1500x1500" in line.parsed_name
    assert "1150" not in line.parsed_name


def test_a_real_range_still_reads_as_one() -> None:
    """The range syntax is used: "10-15 dona" means somewhere between."""
    lines = parse_basket_lines("sement 10-15 qop")
    assert len(lines) == 1
    assert lines[0].qty > Decimal("0")


def test_the_thickness_survives_the_quantity() -> None:
    """ "03m 10ta fanera": three millimetres, ten sheets -- in that order."""
    lines = parse_basket_lines("03m 10ta fanera")

    assert len(lines) == 1
    line = lines[0]
    assert line.qty == Decimal("10")
    assert "3mm" in line.parsed_name.replace(" ", "")
    assert "fanera" in line.parsed_name
