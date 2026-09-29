"""What the shop owner reads before confirming a price list.

The old summary said "142 qatordan 118 tasi moslashtirildi" and asked for a
yes. A count is not something you can check: a row read as 5 000 instead of
50 000 looks exactly like a row read correctly until a customer orders at that
price. So the rows themselves are shown, in pages.
"""

from decimal import Decimal

from app.bot.formatters.import_preview import (
    ImportPreviewRow,
    format_import_page,
    format_import_row,
)


def _row(**kwargs: object) -> ImportPreviewRow:
    base: dict[str, object] = {
        "row_no": 1,
        "raw_name": "fanera 12",
        "matched_name": "Fanera 12 mm 1525x1525",
        "price": Decimal("278000"),
        "unit": "dona",
        "qty": Decimal("40"),
        "resolution": "auto",
    }
    base.update(kwargs)
    return ImportPreviewRow(**base)  # type: ignore[arg-type]


def test_a_matched_row_shows_name_price_and_quantity() -> None:
    """The three things the owner was warned to check are the three shown."""
    line = format_import_row(_row(), lang="uz_latn")

    assert "Fanera 12 mm 1525x1525" in line
    assert "278 000" in line, "price must be readable, not 278000"
    assert "40 dona" in line
    assert line.startswith("1. ✅")


def test_a_row_needing_review_is_marked_and_keeps_the_owner_s_words() -> None:
    line = format_import_row(_row(resolution="manual", matched_name=None), lang="uz_latn")

    assert "⚠️" in line
    assert "«fanera 12»" in line, "unmatched rows show what the file actually said"


def test_a_skipped_row_says_so() -> None:
    line = format_import_row(_row(resolution="skipped"), lang="uz_latn")
    assert line.startswith("1. ❌")


def test_a_missing_price_is_named_not_blank() -> None:
    """A blank where a price should be reads as zero, which is worse than absent."""
    line = format_import_row(_row(price=None), lang="uz_latn")
    assert "278" not in line
    assert line.strip().endswith(("yo'q", "нет", "йўқ")) or "narx" in line.lower()


def test_the_page_says_where_the_owner_is() -> None:
    rows = [_row(row_no=n) for n in range(1, 21)]
    page = format_import_page(rows, page=2, total_pages=8, total_rows=142, lang="uz_latn")

    assert "2" in page and "8" in page and "142" in page
    assert page.count("\n") >= 20


def test_an_empty_page_does_not_pretend_to_have_rows() -> None:
    page = format_import_page([], page=1, total_pages=1, total_rows=0, lang="uz_latn")
    assert "0" in page


def test_names_from_the_file_are_escaped() -> None:
    """A price list is a file from outside; its text reaches Telegram as HTML."""
    line = format_import_row(
        _row(raw_name="<b>hack", matched_name=None, resolution="manual"), lang="uz_latn"
    )
    assert "<b>hack" not in line
    assert "&lt;b&gt;hack" in line
