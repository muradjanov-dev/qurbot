"""Render a QuoteVariant as a downloadable PDF price offer.

Synchronous/CPU-bound (reportlab draws on an in-memory canvas), so callers
must run generate_quote_pdf via asyncio.to_thread rather than call it
directly from an async handler.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.bot.formatters.common import format_qty
from app.domain.optimizer.models import QuoteVariant


def _fmt_uzs(amount: Decimal) -> str:
    return f"{amount:,.0f} so'm"


def generate_quote_pdf(variant: QuoteVariant, order_id: int | None = None) -> bytes:
    """Render a quote variant to PDF bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QurBotTitle", parent=styles["Title"], fontSize=18, spaceAfter=2 * mm
    )
    shop_style = ParagraphStyle(
        "ShopHeader", parent=styles["Heading2"], fontSize=12, spaceBefore=4 * mm
    )
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.grey)

    story: list[Any] = []

    title = "QurBot — Narxlar taklifi"
    if order_id is not None:
        title += f" (Buyurtma #{order_id})"
    story.append(Paragraph(title, title_style))

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Yaratilgan sana: {generated_at}", meta_style))
    story.append(Spacer(1, 6 * mm))

    for group in variant.shop_groups:
        header = group.shop_name
        if group.distance_km:
            header += f" ({group.distance_km:.1f} km)"
        story.append(Paragraph(header, shop_style))

        rows = [["Mahsulot", "Miqdor", "Narx"]]
        for line in group.lines:
            rows.append(
                [
                    line.product_name,
                    f"{format_qty(line.billed_qty)} {line.pack_unit}",
                    _fmt_uzs(line.line_cost_uzs),
                ]
            )
        delivery_str = "Bepul" if group.is_free_delivery else _fmt_uzs(group.delivery_fee_uzs)
        rows.append(["", "Yetkazib berish", delivery_str])
        rows.append(["", "Jami", _fmt_uzs(group.shop_total_uzs)])

        table = Table(rows, colWidths=[90 * mm, 40 * mm, 40 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f4f4f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -3),
                        [colors.white, colors.HexColor("#f5f5f5")],
                    ),
                    ("LINEABOVE", (0, -2), (-1, -2), 0.8, colors.black),
                ]
            )
        )
        story.append(table)

    story.append(Spacer(1, 8 * mm))

    summary_rows = [
        ["Mahsulotlar narxi", _fmt_uzs(variant.items_total_uzs)],
        ["Yetkazib berish", _fmt_uzs(variant.delivery_total_uzs)],
        ["Jami", _fmt_uzs(variant.grand_total_uzs)],
    ]
    summary_table = Table(summary_rows, colWidths=[130 * mm, 40 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 12),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(summary_table)

    doc.build(story)
    return buf.getvalue()
