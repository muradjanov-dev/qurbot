"""The fastener price list, as the catalogue reads it back.

The list is four pages of blocks, and two properties decide whether it is
usable: a row must be reachable by the words and sizes a customer types, and no
two rows may claim the same phrasing -- an approved alias is an auto-accept, so
a shared one would silently pick a price.
"""

from decimal import Decimal

import pytest

from app.domain.normalize.text import normalize_query
from app.domain.parsing.parser import parse_basket_lines
from scripts.seed import (
    _METIZ,
    _METIZ_CATEGORY,
    USD_TO_UZS,
    expand_metiz_label,
    generate_aliases_for_product,
    generate_catalog_data,
)

_METIZ_ROW_COUNT = 232


@pytest.fixture(scope="module")
def catalog() -> list:
    return generate_catalog_data()


@pytest.fixture(scope="module")
def metiz(catalog: list) -> list:
    return [item for item in catalog if item.category_slug == _METIZ_CATEGORY]


def test_every_printed_row_became_a_product(metiz: list) -> None:
    assert len(metiz) == _METIZ_ROW_COUNT
    assert sum(len(group.rows) for group in _METIZ) == _METIZ_ROW_COUNT


def test_every_row_carries_a_price(metiz: list) -> None:
    """Unlike the timber, this list came with money on it."""
    assert all(item.reference_price is not None for item in metiz)
    assert all(item.reference_price > Decimal("0") for item in metiz)


def test_prices_are_converted_at_the_one_written_down_rate(metiz: list) -> None:
    """The cheapest row on the list is a 0.012 $ rivet; nothing is free."""
    cheapest = min(item.reference_price for item in metiz)
    assert cheapest == (Decimal("0.012") * USD_TO_UZS).quantize(Decimal("1"))


def test_the_unit_travels_with_the_block(metiz: list) -> None:
    """Piece, kilo, box and pack all appear, and they are not interchangeable."""
    units = {item.base_unit for item in metiz}
    assert units == {"dona", "kg", "quti", "pachka"}

    by_slug = {item.slug: item for item in metiz}
    assert by_slug["mix-16-20"].base_unit == "kg"
    assert by_slug["oq-anker-10x72"].base_unit == "dona"
    assert by_slug["zaklepka-orbita-3-2x11"].base_unit == "pachka"
    assert by_slug["chopiq-qizil-6x30"].base_unit == "quti"


class TestLabelExpansion:
    """A label is a size, a list of sizes, or a span between two of them."""

    def test_a_lone_size_stays_one(self) -> None:
        assert expand_metiz_label("10x72") == ["10x72"]
        assert expand_metiz_label("5x16x16") == ["5x16x16"]

    def test_a_list_is_taken_as_printed(self) -> None:
        """ "3x13-16-20-25" spells out four screws; it is not 13 through 25."""
        assert expand_metiz_label("3x13-16-20-25") == [
            "3x13-16-20-25",
            "3x13",
            "3x16",
            "3x20",
            "3x25",
        ]
        assert expand_metiz_label("4.2x16;19;25;32")[1:] == [
            "4.2x16",
            "4.2x19",
            "4.2x25",
            "4.2x32",
        ]

    def test_a_span_over_the_length_fills_in(self) -> None:
        """One price per kilo from 13 to 76 mm, so 4.2x25 must find this row."""
        sizes = expand_metiz_label("4.2x13-76")
        assert "4.2x25" in sizes
        assert "4.2x13" in sizes and "4.2x76" in sizes

    def test_a_span_over_both_numbers_fills_in(self) -> None:
        sizes = expand_metiz_label("6x50-12x150")
        assert "6x50" in sizes and "12x150" in sizes
        assert "10x100" in sizes, "a diameter inside the span is inside the price"

    def test_a_fractional_end_is_kept_even_though_it_is_off_the_ladder(self) -> None:
        assert "3.5x16" in expand_metiz_label("3.5x16-4x16")

    def test_nothing_outside_the_span_is_invented(self) -> None:
        sizes = expand_metiz_label("16-19")
        assert "20" not in sizes
        assert "15" not in sizes

    def test_a_threaded_span_is_not_filled_in(self) -> None:
        """M6 to M24 is a thread series, not a millimetre ladder."""
        assert expand_metiz_label("m6-m24") == ["m6-m24", "m6", "m24"]


def test_no_two_products_claim_the_same_phrasing(catalog: list) -> None:
    """An approved alias auto-accepts, so a shared one picks a price silently.

    The generic family words ("samorez 4.8x25") are deliberately absent for
    exactly this reason: eight blocks sell one, and that question belongs to
    the customer, not to whichever row seeded first.
    """
    metiz_slugs = {item.slug for item in catalog if item.category_slug == _METIZ_CATEGORY}
    owner: dict[str, str] = {}
    clashes: list[tuple[str, str, str]] = []
    for item in catalog:
        for alias in generate_aliases_for_product(item):
            norm = alias["alias_norm"]
            previous = owner.setdefault(norm, item.slug)
            if previous != item.slug and (item.slug in metiz_slugs or previous in metiz_slugs):
                clashes.append((norm, previous, item.slug))

    assert clashes == []


@pytest.mark.parametrize(
    ("message", "expected_name"),
    [
        ("10 kg sariq samorez 3x25", "Sariq samorez 3x13-16-20-25"),
        ("5 kg саморез потай 4,2х25", "Potay samorez 4.2x16;19;25;32"),
        ("aka menga 50 dona sariq anker 10x100 kere", "Sariq anker 10x100"),
        ("20 kg mix 70", "Mix 70-200"),
        ("4 pachka zaklepka orbita 4x16", "Zaklepka Orbita 4x16"),
        ("5 kg medved 7.5x100", "Medved montajniy 7.5x72-202"),
        ("болты 12х100 3 кг", "Bolt 12x30-12x150"),
        ("3 kg press shayba ostriy 4.2x25", "Press shayba (o'tkir) 4.2x13-76"),
        ("2 пач заклепка орбита 5х20", "Zaklepka Orbita 5x20"),
        ("1 kg chopiq qizil babochka", "Chopiq qizil (m/plast) babochka"),
    ],
)
def test_an_order_lands_on_the_row_it_named(
    catalog: list, message: str, expected_name: str
) -> None:
    """Stage 1, for nothing: no scoring, no model, no cost."""
    aliases: dict[str, str] = {}
    for item in catalog:
        for alias in generate_aliases_for_product(item):
            aliases.setdefault(alias["alias_norm"], item.name_uz)

    lines = parse_basket_lines(message)
    assert len(lines) == 1
    assert aliases.get(normalize_query(lines[0].parsed_name).text_norm) == expected_name


@pytest.mark.parametrize("message", ["2 kg samorez 4.8x40", "20 dona anker 12x150"])
def test_a_bare_family_word_is_left_for_the_customer_to_settle(catalog: list, message: str) -> None:
    """Eight blocks sell a samorez 4.8x40 at eight prices.

    No alias may answer this on its own; it has to reach scoring, where the
    bot puts the choice back to the person who asked.
    """
    aliases = {
        alias["alias_norm"] for item in catalog for alias in generate_aliases_for_product(item)
    }
    lines = parse_basket_lines(message)
    assert normalize_query(lines[0].parsed_name).text_norm not in aliases
