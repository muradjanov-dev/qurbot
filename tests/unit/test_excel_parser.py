"""Unit tests for the Excel/CSV domain parser.

Tests are pure — no DB, no network. Uses openpyxl to generate
test Excel files in-memory.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from openpyxl import Workbook

from app.domain.parsing.excel_parser import (
    ParseFileResult,
    _detect_columns,
    parse_csv,
    parse_excel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_excel_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    """Create an in-memory .xlsx file and return its bytes."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_csv_bytes(
    headers: list[str], rows: list[list[str]], encoding: str = "utf-8", delimiter: str = ","
) -> bytes:
    """Create an in-memory CSV file and return its bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode(encoding)


# ---------------------------------------------------------------------------
# Column Detection
# ---------------------------------------------------------------------------


class TestColumnDetection:
    def test_detect_uz_latin_headers(self) -> None:
        headers = ["Nomi", "Narxi", "Birlik", "Qadoq", "Miqdor"]
        detected = _detect_columns(headers)
        assert detected["name"] == 0
        assert detected["price"] == 1
        assert detected["unit"] == 2
        assert detected["pack_size"] == 3
        assert detected["qty"] == 4

    def test_detect_russian_headers(self) -> None:
        headers = ["Наименование", "Цена", "Ед. изм", "Фасовка", "Количество"]
        detected = _detect_columns(headers)
        assert detected["name"] == 0
        assert detected["price"] == 1
        assert detected["unit"] == 2
        assert detected["pack_size"] == 3
        assert detected["qty"] == 4

    def test_detect_english_headers(self) -> None:
        headers = ["Product Name", "Price", "Unit", "Pack Size", "Quantity"]
        detected = _detect_columns(headers)
        assert detected["name"] == 0
        assert detected["price"] == 1
        assert detected["unit"] == 2
        assert detected["pack_size"] == 3
        assert detected["qty"] == 4

    def test_detect_mixed_headers(self) -> None:
        headers = ["Mahsulot nomi", "Сумма", "birlik"]
        detected = _detect_columns(headers)
        assert detected["name"] == 0
        assert detected["price"] == 1
        assert detected["unit"] == 2

    def test_missing_columns_handled(self) -> None:
        headers = ["Nomi", "Narxi"]
        detected = _detect_columns(headers)
        assert "name" in detected
        assert "price" in detected
        assert "unit" not in detected

    def test_empty_headers(self) -> None:
        headers = ["", "", ""]
        detected = _detect_columns(headers)
        assert len(detected) == 0


# ---------------------------------------------------------------------------
# Excel Parser
# ---------------------------------------------------------------------------


class TestExcelParser:
    def test_parse_valid_excel_uz_headers(self) -> None:
        data = _make_excel_bytes(
            headers=["Nomi", "Narxi", "Birlik"],
            rows=[
                ["Sement M400", 52000, "qop"],
                ["G'isht qizil", 1400, "dona"],
                ["Armatura d12", 18500, "kg"],
            ],
        )
        result = parse_excel(data)
        assert isinstance(result, ParseFileResult)
        assert len(result.rows) == 3
        assert result.total_rows == 3
        assert result.skipped_rows == 0
        assert result.rows[0].raw_name == "Sement M400"
        assert result.rows[0].raw_price == Decimal("52000")
        assert result.rows[0].raw_unit == "qop"

    def test_parse_russian_headers(self) -> None:
        data = _make_excel_bytes(
            headers=["Наименование", "Цена", "Ед. изм", "Фасовка"],
            rows=[
                ["Цемент М400", 53000, "мешок", 50],
                ["Кирпич красный", 1500, "шт", 1],
            ],
        )
        result = parse_excel(data)
        assert len(result.rows) == 2
        assert result.detected_columns["name"] == 0
        assert result.detected_columns["price"] == 1
        assert result.rows[0].raw_pack_size == Decimal("50")

    def test_skip_empty_name_rows(self) -> None:
        data = _make_excel_bytes(
            headers=["Nomi", "Narxi"],
            rows=[
                ["Sement M400", 52000],
                [None, 30000],  # No name — skip
                ["", 25000],  # Empty name — skip
                ["Armatura", 18000],
            ],
        )
        result = parse_excel(data)
        assert len(result.rows) == 2
        assert result.skipped_rows == 2

    def test_handle_decimal_prices(self) -> None:
        data = _make_excel_bytes(
            headers=["Nomi", "Narxi"],
            rows=[
                ["Bo'yoq", "125,500"],  # Comma as thousands separator
                ["Lak", "52.5"],  # Dot as decimal
            ],
        )
        result = parse_excel(data)
        assert result.rows[0].raw_price == Decimal("125500")
        assert result.rows[1].raw_price == Decimal("52.5")

    def test_extra_columns_collected(self) -> None:
        data = _make_excel_bytes(
            headers=["Nomi", "Narxi", "Izoh"],
            rows=[["Sement", 52000, "M400 grade"]],
        )
        result = parse_excel(data)
        # "Izoh" is not a recognized column, so it goes to extra
        assert "col_2" in result.rows[0].extra_columns
        assert result.rows[0].extra_columns["col_2"] == "M400 grade"

    def test_empty_excel(self) -> None:
        wb = Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        result = parse_excel(buf.getvalue())
        assert len(result.rows) == 0

    def test_150_row_stress(self) -> None:
        """SPEC deliverable: 150-row Excel imports successfully."""
        rows = [[f"Mahsulot #{i}", 10000 + i * 100, "dona"] for i in range(150)]
        data = _make_excel_bytes(
            headers=["Mahsulot nomi", "Narxi", "Birlik"],
            rows=rows,
        )
        result = parse_excel(data)
        assert len(result.rows) == 150
        assert result.total_rows == 150
        assert result.skipped_rows == 0

    def test_no_header_fallback(self) -> None:
        """When headers can't be detected, assume col0=name, col1=price."""
        data = _make_excel_bytes(
            headers=["ABC", "DEF"],
            rows=[["Sement", 52000]],
        )
        result = parse_excel(data)
        # Should still parse with fallback detection
        assert len(result.rows) >= 1


# ---------------------------------------------------------------------------
# CSV Parser
# ---------------------------------------------------------------------------


class TestCsvParser:
    def test_parse_utf8_csv(self) -> None:
        data = _make_csv_bytes(
            headers=["Nomi", "Narxi", "Birlik"],
            rows=[
                ["Sement M400", "52000", "qop"],
                ["G'isht", "1400", "dona"],
            ],
        )
        result = parse_csv(data)
        assert len(result.rows) == 2
        assert result.rows[0].raw_name == "Sement M400"
        assert result.rows[0].raw_price == Decimal("52000")

    def test_parse_cp1251_csv(self) -> None:
        """Russian Windows encoding fallback."""
        data = _make_csv_bytes(
            headers=["Наименование", "Цена"],
            rows=[["Цемент", "53000"]],
            encoding="cp1251",
        )
        result = parse_csv(data, encoding="cp1251")
        assert len(result.rows) == 1
        assert result.rows[0].raw_name == "Цемент"

    def test_parse_semicolon_delimiter(self) -> None:
        data = _make_csv_bytes(
            headers=["Nomi", "Narxi"],
            rows=[["Sement", "52000"]],
            delimiter=";",
        )
        result = parse_csv(data)
        assert len(result.rows) == 1

    def test_parse_empty_csv(self) -> None:
        result = parse_csv(b"")
        assert len(result.rows) == 0

    def test_150_row_csv_stress(self) -> None:
        rows = [[f"Product {i}", str(10000 + i)] for i in range(150)]
        data = _make_csv_bytes(
            headers=["Product Name", "Price"],
            rows=rows,
        )
        result = parse_csv(data)
        assert len(result.rows) == 150
