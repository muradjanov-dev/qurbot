"""Literal supplier identities must not duplicate their transcribed catalog rows."""

from copy import deepcopy
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct, Category, Unit
from scripts.catalog_import import _exact, import_rows, read_workbook
from scripts.seed import generate_catalog_data


def write_book(path: Path, rows: list[list[object]]) -> None:
    book = Workbook()
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()


SOURCE_CASES = [
    ("ОК АНКЕР", "10х72", "шт", "oq-anker-10x72"),
    ("ОК АНКЕР", "10х92", "шт", "oq-anker-10x92"),
    ("САРИК АНКЕР", "10х80", "шт", "sariq-anker-10x80"),
    ("МУФТА СOEДИНИТЕЛ", "6", "шт", "mufta-soedinitel-6"),
    ("КРОВЕЛЬНЫЙ САМОРЕЗ РАНГЛИ", "4,8х25", "коробкa", "krovelniy-samorez-rangli-4-8x25"),
    ("КРОВЕЛЬНЫЙ САМОРЕЗ ОК", "4,8х25", "коробка", "krovelniy-samorez-oq-4-8x25"),
    ("ЗАКЛЕПКА ORBITA", "3,2х11", "пачка", "zaklepka-orbita-3-2x11"),
    ("ЦАНГА ORBITA", "М 8", "шт", "tsanga-orbita-m8"),
    ("ЦАНГА ТУРЕЦКИЙ", "М 8", "шт", "tsanga-turk-m8"),
    ("КРЮЧОК САРИК", "М 6x60", "шт", "kryuchok-sariq-m6x60"),
    ("КРЮЧОК ЁПИК", "M 8x60", "шт", "kryuchok-yopiq-m8x60"),
    ("ЧОПИК КИЗИЛ М / ПЛАСТ", "Бабочка", "коробкa", "chopiq-qizil-babochka"),
    ("ЗОНТИК М / ПЛАСТ", "Термо 120", "пачка", "zontik-mplast-termo-120"),
    ("ШПИЛЬКА 0,97", "6", "шт", "shpilka-097-6"),
    ("ШПИЛЬКА 1метр ОРИГИНАЛ", "8", "шт", "shpilka-1m-8"),
    ("ШПИЛЬКА 2 метр", "8", "шт", "shpilka-2m-8"),
    ("КРЮЧОК АРМСТРОН", "6х40", "шт", "kryuchok-armstrong-6x40"),
]


async def test_source_mapping_preserves_existing_rows_and_separates_variants(
    test_session: AsyncSession, tmp_path: Path
) -> None:
    path = tmp_path / "samarez mix.xlsx"
    write_book(
        path,
        [
            ["№", "", "Наименования", "ед", "Цена"],
            *[
                [index, name, size, unit, 999]
                for index, (name, size, unit, _) in enumerate(SOURCE_CASES, 1)
            ],
        ],
    )
    rows, held = read_workbook(path)
    assert not held
    expected = [case[3] for case in SOURCE_CASES]
    assert [row.legacy_slug for row in rows] == expected
    assert all(row.reference_price is None for row in rows)
    catalog = {item.slug: item for item in generate_catalog_data()}
    async with test_session.begin():
        category_id = (
            await test_session.execute(
                insert(Category)
                .values(slug="mahkamlash-materiallari", name_uz="Test", name_ru="Test")
                .returning(Category.id)
            )
        ).scalar_one()
        for unit in {catalog[slug].base_unit for slug in expected}:
            await test_session.execute(
                insert(Unit).values(code=unit, name_uz=unit, name_ru=unit, dimension="count")
            )
        for slug in expected:
            item = catalog[slug]
            await test_session.execute(
                insert(CanonicalProduct).values(
                    slug=item.slug,
                    name_uz=item.name_uz,
                    name_uz_cyrl=item.name_uz_cyrl,
                    name_ru=item.name_ru,
                    brand=item.brand,
                    base_unit_code=item.base_unit,
                    category_id=category_id,
                    attributes={**item.attributes, "operator_note": "keep"},
                    source=item.source,
                    source_ref=item.source_ref,
                    reference_price=item.reference_price,
                    is_active=False,
                    search_doc="unchanged",
                )
            )
    async with test_session.begin():
        before = (await test_session.execute(select(CanonicalProduct.__table__))).mappings().all()
    for _ in range(2):
        decisions = await import_rows(test_session, rows, apply=True)
        assert all(d["action"] == "existing" for d in decisions)
        assert len({d["canonical_id"] for d in decisions}) == len(expected)
    async with test_session.begin():
        after = (await test_session.execute(select(CanonicalProduct.__table__))).mappings().all()
    assert before == after
    original = dict(before[0])
    for field, value in (
        ("base_unit_code", "kg"),
        ("brand", "Other"),
        ("source_ref", "other-source"),
    ):
        changed = {**original, field: value}
        assert not _exact(rows[0], changed)
    changed = deepcopy(original)
    changed["attributes"]["size"] = "10x92"
    assert not _exact(rows[0], changed)
    # Same source slug with different details is a hold, never a new duplicate.
    async with test_session.begin():
        product = await test_session.get(CanonicalProduct, before[0]["id"])
        product.attributes = changed["attributes"]
    result = await import_rows(test_session, [rows[0]], apply=True)
    assert result[0]["action"] == "review"
    assert result[0]["candidate_ids"] == [before[0]["id"]]


def test_supplier_held_sheets_are_not_repaired_or_added(tmp_path: Path) -> None:
    path = tmp_path / "fanera.xlsx"
    write_book(
        path,
        [
            [
                "Mahsulot nomi",
                "Ishlab chiqaruvchi",
                "",
                "O'lcham (mm)",
                "Qalinlik (mm)",
                "Narx (So’m/dona)",
            ],
            ["HDF", "Rossiya (Kronospan)", "Oq", "2800×2071", "3.2 (4)", "-"],
            ["DSP", "Rossiya (Kronospan)", "", "2750×1830", "1.6", 260000],
            ["DSP", "Rossiya (Yekaterinburg)", "", "3500×1750", "1.6", 302000],
            ["DSP", "Rossiya (Murim)", "", "3500×1750", "1.6", 321000],
            ["DSP", "Rossiya (Perm)", "", "3500×1750", "1.6", 375000],
        ],
    )
    rows, held = read_workbook(path)
    assert not rows
    assert len(held) == 5
    assert held[0]["cells"][3] == "2800×2071"
    assert held[1]["cells"][4] == "1.6"
    assert [r["row"] for r in held] == [2, 3, 4, 5, 6]


def test_ambiguous_labels_units_and_lists_require_review(tmp_path: Path) -> None:
    path = tmp_path / "samarez mix.xlsx"
    write_book(
        path,
        [
            ["№", "", "Наименования", "ед", "Цена"],
            [1, "ПОТТАЙ САМОРЕЗ", "4,2х16;19;25;32", "кг", 2],
            [2, "ШАЙБА КАТТ ВА КИЧИК", "M 4; M 5", "кг", 2],
            [3, "ШПИЛЬКА 0,98", "8", "шт", 2],
            [4, "ОК АНКЕР", "10х72", "кг", 2],
            [5, "ОК АНКЕР", "10х72", "unknown", 2],
            [6, "ОК АНКЕР NEW BRAND", "10х72", "шт", 2],
        ],
    )
    rows, held = read_workbook(path)
    assert not rows
    assert len(held) == 6
