"""What survives when a product name is wider than a button.

Telegram gives an inline button one line and clips the overflow from the
right. On this catalogue that throws away the size -- three roofing screws
whose names differ only after the twentieth character arrived as three
identical-looking buttons, and the customer was asked to pick one.
"""

import pytest

from app.bot.formatters.common import shorten_button_label


@pytest.mark.parametrize(
    "name",
    [
        "Zaklepka Orbita 3.2x11",
        "Chopiq kulrang (m/plast) 6x30",
        "Krovelniy samorez oq 4.8x50",
    ],
)
def test_a_name_that_fits_is_left_alone(name: str) -> None:
    assert shorten_button_label(name, 34) == name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "Krovelniy samorez oq (metallga) 6.3x25-200",
            "Krovelniy… (metallga) 6.3x25-200",
        ),
        (
            "Fanera laminatsiyalangan SiyPly 18 mm (2440x1220)",
            "Fanera… SiyPly 18 mm (2440x1220)",
        ),
        (
            "Fanera berezovaya 3x3 12 mm (1525x1525)",
            "Fanera… 3x3 12 mm (1525x1525)",
        ),
    ],
)
def test_the_size_is_what_survives(name: str, expected: str) -> None:
    """The end of the name is what tells two rows apart, so the middle goes."""
    shortened = shorten_button_label(name, 34)
    assert shortened == expected
    assert len(shortened) <= 34


def test_two_rows_that_differ_only_late_stay_distinguishable() -> None:
    """The reported failure: both buttons read the same after clipping."""
    metallga = shorten_button_label("Krovelniy samorez oq (metallga) 6.3x25-200", 34)
    plain = shorten_button_label("Krovelniy samorez oq 6.3x25-200", 34)
    assert metallga != plain


def test_the_family_word_is_always_kept() -> None:
    assert shorten_button_label("Fanera laminatsiyalangan SiyPly 18 mm", 20).startswith("Fanera")


def test_one_long_word_is_simply_cut() -> None:
    """Nothing to elide around, so the limit is still honoured."""
    assert shorten_button_label("Superuzunnomsizbosqichliyagonasozmahsulot", 20) == (
        "Superuzunnomsizbosqi"
    )


def test_whitespace_is_normalized_first() -> None:
    assert shorten_button_label("  Mufta   (biriktiruvchi)  10 ", 34) == "Mufta (biriktiruvchi) 10"
