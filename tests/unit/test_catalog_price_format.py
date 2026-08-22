"""How a catalogue row's price is rendered.

Before this existed the admin catalogue showed a bare "—" for all 222 rows,
because the only price it knew about came from a live shop offer and no shop
had uploaded one.
"""

from decimal import Decimal

from app.bot.formatters.common import format_catalog_price


def test_live_offer_price_wins() -> None:
    """A shop's live price is the one someone will honour today."""
    assert (
        format_catalog_price(Decimal("150000"), Decimal("157000"), lang="uz_latn") == "150 000 so'm"
    )


def test_falls_back_to_the_supplier_list_price() -> None:
    assert format_catalog_price(None, Decimal("157000"), lang="uz_latn") == "~157 000 so'm"


def test_list_price_is_marked_so_it_does_not_read_as_a_quote() -> None:
    assert format_catalog_price(None, Decimal("157000"), lang="uz_latn").startswith("~")
    assert not format_catalog_price(Decimal("157000"), None, lang="uz_latn").startswith("~")


def test_no_price_at_all_is_negotiable_not_zero() -> None:
    """The price lists say "Kelishiladi"; rendering 0 would be a lie."""
    assert format_catalog_price(None, None, lang="uz_latn") == "Kelishiladi"
    assert format_catalog_price(None, None, lang="ru") == "Договорная"


def test_currency_follows_the_language() -> None:
    assert format_catalog_price(Decimal("60000"), None, lang="ru") == "60 000 сум"
    assert format_catalog_price(Decimal("60000"), None, lang="uz_cyrl") == "60 000 сўм"
