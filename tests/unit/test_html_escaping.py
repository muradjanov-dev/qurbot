"""User-supplied text must never reach Telegram as raw HTML.

The bot sends with ParseMode.HTML. An unclosed tag in user input makes
Telegram reject the entire message ("can't parse entities"), which the user
experiences as the bot being broken -- so these are availability tests as
much as injection tests.
"""

from app.bot.formatters.common import esc
from app.bot.handlers.customer import _format_parse_table


def test_esc_neutralises_markup() -> None:
    assert esc("<b>hack") == "&lt;b&gt;hack"
    assert esc("a & b") == "a &amp; b"
    assert esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_parse_table_escapes_unmatched_raw_text() -> None:
    lines = [
        {
            "line_no": 1,
            "qty": "5",
            "unit_code": "dona",
            "status": "unresolved",
            "raw_text": "<b>hack",
            "parsed_name": "x",
            "canonical_name": "x",
        }
    ]
    out = _format_parse_table(lines, lang="uz_latn")
    assert "<b>hack" not in out
    assert "&lt;b&gt;hack" in out
    # The template's own markup must survive.
    assert "<i>katalogda topilmadi</i>" in out


def test_parse_table_escapes_matched_and_ambiguous_names() -> None:
    lines = [
        {
            "line_no": 1,
            "qty": "1",
            "unit_code": "dona",
            "status": "auto_accept",
            "raw_text": "r",
            "parsed_name": "p",
            "canonical_name": "<i>Sement",
        },
        {
            "line_no": 2,
            "qty": "2",
            "unit_code": "qop",
            "status": "ask_user",
            "raw_text": "r2",
            "parsed_name": "<u>Gisht",
            "canonical_name": "c",
        },
    ]
    out = _format_parse_table(lines, lang="uz_latn")
    assert "<i>Sement" not in out
    assert "&lt;i&gt;Sement" in out
    assert "<u>Gisht" not in out
    assert "&lt;u&gt;Gisht" in out


def test_parse_table_balances_tags_for_adversarial_input() -> None:
    """Every '<' that survives must belong to one of the template's own tags."""
    lines = [
        {
            "line_no": i,
            "qty": "1",
            "unit_code": "dona",
            "status": status,
            "raw_text": "</b><script>",
            "parsed_name": "</i>&<b",
            "canonical_name": "<<>>",
        }
        for i, status in enumerate(("auto_accept", "ask_user", "unresolved"), start=1)
    ]
    out = _format_parse_table(lines, lang="uz_latn")
    assert out.count("<b>") == out.count("</b>")
    assert out.count("<i>") == out.count("</i>")
    assert "<script>" not in out


def test_parse_table_explains_a_refused_quantity() -> None:
    """An unorderable quantity must say so, not read as 'not in catalog'."""
    lines = [
        {
            "line_no": 1,
            "qty": "-5",
            "unit_code": "dona",
            "status": "unresolved",
            "method": "invalid_qty",
            "raw_text": "-5 dona sement",
            "parsed_name": "sement",
            "canonical_name": "sement",
        },
        {
            "line_no": 2,
            "qty": "1",
            "unit_code": "dona",
            "status": "unresolved",
            "method": "trgm",
            "raw_text": "kosmik kema",
            "parsed_name": "kosmik kema",
            "canonical_name": "kosmik kema",
        },
    ]
    out = _format_parse_table(lines, lang="uz_latn")
    assert "1 000 000" in out
    assert "katalogda topilmadi" in out
