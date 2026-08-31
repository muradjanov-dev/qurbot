"""Show a shop owner what was read out of their price list, page by page.

The import summary counted rows -- "142 qatordan 118 tasi moslashtirildi" --
and then asked for a confirmation. That is a number to agree with, not the
content: nobody could see that row 37 had been read as 5 000 so'm instead of
50 000 until a customer ordered at the wrong price. A price list is long, so
the content comes in pages the owner can walk through before confirming.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.bot.formatters.common import esc, format_qty
from app.core.i18n import t


@dataclass(frozen=True)
class ImportPreviewRow:
    """One staged row, as the owner needs to check it: name, price, quantity."""

    row_no: int
    raw_name: str
    matched_name: str | None
    price: Decimal | None
    unit: str | None
    qty: Decimal | None
    resolution: str


def _price_part(row: ImportPreviewRow, lang: str) -> str:
    if row.price is None:
        return t("import_row_no_price", lang=lang)
    unit = f" / {esc(row.unit)}" if row.unit else ""
    return f"<b>{row.price:,.0f}</b> so'm{unit}".replace(",", " ")


def format_import_row(row: ImportPreviewRow, lang: str) -> str:
    """One line: what was read, what it matched, and for how much."""
    if row.resolution == "skipped":
        return f"{row.row_no}. ❌ «{esc(row.raw_name)}» — " + t("import_row_skipped", lang=lang)

    name = esc(row.matched_name) if row.matched_name else f"«{esc(row.raw_name)}»"
    mark = "✅" if row.resolution == "auto" and row.matched_name else "⚠️"
    parts = [f"{row.row_no}. {mark} {name} — {_price_part(row, lang)}"]

    if row.qty is not None:
        parts.append(f" · {format_qty(row.qty)} {esc(row.unit or 'dona')}")
    if row.resolution != "auto":
        parts.append("\n     " + t("import_row_needs_review", lang=lang))
    return "".join(parts)


def format_import_page(
    rows: list[ImportPreviewRow],
    *,
    page: int,
    total_pages: int,
    total_rows: int,
    lang: str,
) -> str:
    """Render one page of a staged import, with its place in the whole.

    `page` is 1-based, because it is shown to a person.
    """
    header = t(
        "import_preview_header",
        lang=lang,
        page=page,
        total_pages=max(total_pages, 1),
        total_rows=total_rows,
    )
    if not rows:
        return f"{header}\n\n{t('import_preview_empty', lang=lang)}"

    body = "\n".join(format_import_row(row, lang) for row in rows)
    return f"{header}\n\n{body}"
