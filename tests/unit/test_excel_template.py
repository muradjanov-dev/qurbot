"""The price-list template a shop owner downloads.

The upload screen said "send your Excel here" and nothing else, so a shop
owner had to guess which columns the importer reads. The template is only
worth anything if the importer actually understands it, which is what these
tests pin: the template is fed straight back through the parser.
"""

from decimal import Decimal

import pytest

from app.domain.parsing.excel_parser import parse_excel
from app.domain.parsing.excel_template import (
    TEMPLATE_EXAMPLE_ROWS,
    build_price_template,
)


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
def test_the_importer_understands_its_own_template(lang: str) -> None:
    """Every column the template offers must be one the parser detects."""
    result = parse_excel(build_price_template(lang=lang))

    assert set(result.detected_columns) == {"name", "price", "unit", "pack_size", "qty"}


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
def test_the_example_rows_survive_a_round_trip(lang: str) -> None:
    """The examples are filled-in rows, not placeholders to be deleted."""
    result = parse_excel(build_price_template(lang=lang))

    assert result.total_rows == len(TEMPLATE_EXAMPLE_ROWS)
    assert result.skipped_rows == 0

    first = result.rows[0]
    assert first.raw_name == TEMPLATE_EXAMPLE_ROWS[0][0]
    assert first.raw_price == Decimal(TEMPLATE_EXAMPLE_ROWS[0][2])


def test_the_examples_name_products_the_catalogue_carries() -> None:
    """An example nobody can match teaches the wrong thing."""
    from scripts.seed import generate_catalog_data

    catalogue = {item.name_uz for item in generate_catalog_data()}
    for name, *_ in TEMPLATE_EXAMPLE_ROWS:
        assert name in catalogue, f"template example {name!r} is not in the catalogue"


def test_it_is_a_real_xlsx_file() -> None:
    """Telegram sends whatever bytes we hand it; a broken file fails silently."""
    data = build_price_template(lang="uz_latn")
    assert data[:2] == b"PK", "xlsx is a zip archive"
    assert len(data) > 1000
