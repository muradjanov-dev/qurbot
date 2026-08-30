"""How a plywood buyer actually writes a size, a thickness and a grade.

Straight from the shop floor: the price list says 1525x1525 and 3 mm, and the
customer writes "fanera 1.50×1.50 03mm 10ta". The trade also names the grade
with a slash -- 2/4, 3/3, 2/2 -- which is the one thing an experienced buyer
puts in the message, because it is what the price depends on.

None of that reached the catalog before: the size was in metres, the thickness
carried a leading zero, and the grade used a separator the catalog spells with
an x.
"""

import pytest

from app.domain.normalize.text import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Leading zeros: the price list prints 03, 04, 09 to keep the column
        # aligned, and customers copy that.
        ("fanera 03mm", "fanera 3mm"),
        ("fanera 04", "fanera 4"),
        ("fanera 09 mm", "fanera 9 mm"),
        # A decimal must survive: 3.05 is not 3.5.
        ("dvp 3.05 mm", "dvp 3.05 mm"),
        # Nothing to strip.
        ("fanera 12mm", "fanera 12mm"),
    ],
)
def test_leading_zero_thickness(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Metres in, millimetres out -- the catalog writes 1525x1525.
        ("fanera 1.525x1.525", "fanera 1525x1525"),
        ("fanera 1.525×1.525 3mm", "fanera 1525x1525 3mm"),
        # The 2440x1220 sheet, named the way the trade says it: 1.22 by 2.44.
        # The longer side leads, as the catalog writes it.
        ("fanera 1.22x2.44", "fanera 2440x1220"),
        ("fanera 2.44x1.22", "fanera 2440x1220"),
        # Rounded to the nearest half metre, which is how it is usually said.
        ("fanera 1.5x1.5", "fanera 1500x1500"),
        ("fanera 1.50x1.50 03mm", "fanera 1500x1500 3mm"),
        # Millimetre sizes are already canonical and must not be touched.
        ("plitka 30x30", "plitka 30x30"),
        ("fanera 2440x1220", "fanera 2440x1220"),
    ],
)
def test_metre_sizes_become_millimetres(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fanera 2/4 12mm", "fanera 2x4 12mm"),
        ("fanera 3/3", "fanera 3x3"),
        ("fanera 2/2 sortli", "fanera 2x2 sortli"),
        ("фанера 2/4", "fanera 2x4"),
    ],
)
def test_plywood_grade_slash(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_grade_slash_only_applies_to_plywood() -> None:
    """A slash between small numbers means inches on a pipe, not a grade.

    "1/2 truba" is a half-inch pipe. Rewriting it to "1x2" would turn a real
    product into a size that does not exist, so the rule needs the plywood word
    to be present before it fires.
    """
    assert normalize_text("1/2 truba") == "1/2 quvur"
    assert normalize_text("3/4 kran") == "3/4 kran"


def test_full_line_the_way_a_customer_writes_it() -> None:
    """The example from the shop: everything wrong at once, still readable."""
    assert normalize_text("fanera 1.50×1.50 03mm") == "fanera 1500x1500 3mm"
    assert normalize_text("Fanera 2/4 1.22×2.44 09mm") == "fanera 2x4 2440x1220 9mm"
