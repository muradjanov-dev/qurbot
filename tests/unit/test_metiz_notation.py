"""How the fastener price list is written, and how customers write it back.

Metiz is the first block of the catalogue that is not sheet goods, and it
arrives in a notation the earlier code had never been shown: sizes with a
decimal comma, packaging units the list abbreviates, and product names that
happen to end in the letter the diameter regex was watching for.
"""

from decimal import Decimal

import pytest

from app.domain.normalize.slang import expand_slang
from app.domain.normalize.text import normalize_text, unify_unit_str
from app.domain.parsing.parser import parse_basket_lines


def test_a_name_ending_in_d_keeps_its_size() -> None:
    """ "medved 7,5x72-202" is a product and a size, not a diameter.

    The bare "d" in the diameter pattern had no word boundary in front of it,
    so it also matched the last letter of the word before: the whole line came
    out as "medved7.5x72", one token that matches nothing in the catalogue.
    """
    assert normalize_text("medved 7.5x100") == "medved 7.5x100"
    assert normalize_text("medved 7,5x72-202").startswith("medved 7.5x72")


def test_a_real_diameter_still_reads_as_one() -> None:
    assert "d12" in normalize_text("armatura d12")
    assert "d12" in normalize_text("armatura d 12")


@pytest.mark.parametrize(
    ("written", "code"),
    [
        ("кор", "quti"),
        ("korobka", "quti"),
        ("коробка", "quti"),
        ("пач", "pachka"),
        ("пачка", "pachka"),
        ("pachka", "pachka"),
        ("upakovka", "pachka"),
    ],
)
def test_the_packaging_units_the_price_list_abbreviates(written: str, code: str) -> None:
    assert unify_unit_str(written) == code


def test_a_pack_is_read_as_a_quantity_not_a_product_word() -> None:
    """Unrecognised, "pachka" travelled into the product name and matched nothing."""
    lines = parse_basket_lines("4 pachka zaklepka orbita 4x16")

    assert len(lines) == 1
    line = lines[0]
    assert line.qty == Decimal("4")
    assert line.unit_code == "pachka"
    assert "pachka" not in line.parsed_name
    assert line.parsed_name == "zaklepka orbita 4x16"


def test_a_box_is_read_as_a_quantity() -> None:
    lines = parse_basket_lines("2 кор saмorez 4,8х40".replace("м", "m"))
    assert lines[0].unit_code == "quti"
    assert lines[0].qty == Decimal("2")


@pytest.mark.parametrize(
    ("typed", "meant"),
    [
        # One word, three coats: bare stem, Russian plural, Uzbek plural.
        ("ankera", "anker"),
        ("ankerlar", "anker"),
        ("samorezy", "samorez"),
        ("samorezlar", "samorez"),
        ("bolty", "bolt"),
        ("gayki", "gayka"),
        ("shayby", "shayba"),
        ("shpilki", "shpilka"),
        ("kryuchki", "kryuchok"),
        ("dyubellar", "dyubel"),
        # The word for the thing, in the other language.
        ("shurup", "samorez"),
        ("ilmoq", "kryuchok"),
        # The supplier's spelling against the catalogue's.
        ("pottay", "potay"),
        ("propka", "probka"),
        ("sarik", "sariq"),
        ("zaklyopka", "zaklepka"),
    ],
)
def test_the_fastener_words_customers_actually_type(typed: str, meant: str) -> None:
    assert expand_slang(typed) == meant


def test_a_cyrillic_fastener_order_survives_the_whole_pipeline() -> None:
    lines = parse_basket_lines("30 кг кровельный саморез ок металлга 6,3х100")

    assert len(lines) == 1
    line = lines[0]
    assert line.qty == Decimal("30")
    assert line.unit_code == "kg"
    assert line.parsed_name == "krovelniy samorez ok metallga 6.3x100"
