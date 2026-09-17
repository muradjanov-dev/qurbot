from argparse import Namespace
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import event, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.shop import District, Shop, ShopProduct
from scripts.catalog_import import import_rows, read_workbook, run


def workbook(tmp_path: Path, name: str, rows: list[list[object]]) -> Path:
    path = tmp_path / name
    book = Workbook()
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()
    return path


SHEET_HEADER = [
    "Mahsulot nomi",
    "Ishlab chiqaruvchi",
    "",
    "O'lcham (mm)",
    "Qalinlik (mm)",
    "Narx (So’m/dona)",
]


async def references(session: AsyncSession) -> None:
    async with session.begin():
        for slug in ("plita-va-fanera", "yogoch", "mahkamlash-materiallari"):
            await session.execute(insert(Category).values(slug=slug, name_uz=slug, name_ru=slug))
        for code in ("dona", "kg", "pachka", "quti"):
            await session.execute(
                insert(Unit).values(
                    code=code,
                    name_uz=code,
                    name_ru=code,
                    dimension="mass" if code == "kg" else "count",
                )
            )


async def test_default_is_offline_and_money_is_not_inferred(tmp_path: Path) -> None:
    path = workbook(
        tmp_path,
        "samarez mix.xlsx",
        [
            ["№", "", "Наименования", "ед", "Цена"],
            [1, "ОК АНКЕР", "10х72", "шт", 0.072],
            [2, "ОК АНКЕР", "10х92", "шт", "=1+1"],
            [3, "БОЛТ", "6х16-6x100", "кг", 1.8],
        ],
    )
    result = await run(Namespace(files=[path], apply=False, database_url=None))
    assert result["mode"] == "dry-run"
    assert result["database_compared"] is False
    assert result["counts"] == {"candidate": 1}
    assert result["review_count"] == 2
    candidate = result["rows"][0]
    assert candidate["currency"] is None
    assert candidate["reference_price"] is None
    assert candidate["attributes"]["price_on_request"] is True
    assert candidate["attributes"]["stock_unverified"] is True
    with pytest.raises(ValueError, match="explicit --database-url"):
        await run(Namespace(files=[path], apply=True, database_url=None))


async def test_environment_database_requires_explicit_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from scripts import catalog_import

    path = workbook(
        tmp_path, "fanera.xlsx", [SHEET_HEADER, ["Fanera", "Rossiya", "2x4", "1525×1525", 3, 54000]]
    )
    url = "postgresql+asyncpg://user:secret@example.invalid/catalog"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    create = MagicMock(return_value=engine)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(catalog_import, "create_async_engine", create)
    monkeypatch.setattr(catalog_import, "async_sessionmaker", lambda _: lambda: session)
    importer = AsyncMock(return_value=[])
    monkeypatch.setattr(catalog_import, "import_rows", importer)
    args = Namespace(files=[path], apply=False, database_url=None, database_env=None)
    assert (await run(args))["database_compared"] is False
    create.assert_not_called()
    args.database_env = "DATABASE_URL"
    result = await run(args)
    assert result["database_compared"] is True
    assert "secret" not in str(result)
    create.assert_called_once_with(url)
    assert importer.call_args.kwargs == {"apply": False}
    args.database_url = url
    with pytest.raises(ValueError, match="mutually exclusive"):
        await run(args)
    args.database_url = None
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="unset or empty"):
        await run(args)


async def test_idempotence_variant_separation_and_read_only_preview(
    test_session: AsyncSession, tmp_path: Path
) -> None:
    await references(test_session)
    path = workbook(
        tmp_path,
        "fanera.xlsx",
        [
            SHEET_HEADER,
            ["Fanera", "Rossiya", "2x4", "1525×1525", 3, 54000],
            ["Fanera", "Rossiya", "3x3", "1525×1525", 3, 52000],
            ["Fanera", "Rossiya", "2x4", "2440×1220", 3, "Kelishiladi"],
            ["Fanera", "Rossiya", "2x4", "1525×1525", 4, 68000],
            ["Fanera", "Xitoy", "2x4", "1525×1525", 3, 40000],
            ["Fanera", "Rossiya", "2x4", "1525×1525", 3, 54000],
        ],
    )
    rows, review = read_workbook(path)
    assert not review
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = test_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        preview = await import_rows(test_session, rows)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert [r["action"] for r in preview] == ["add"] * 5 + ["duplicate"]
    first = await import_rows(test_session, rows, apply=True)
    assert [r["action"] for r in first] == ["add"] * 5 + ["duplicate"]
    # Reordering rows and changing the file checksum/price must not change identity.
    changed = deepcopy(rows)
    changed.reverse()
    for row in changed:
        row.provenance["sha256"] = "f" * 64
        row.reference_price = Decimal("99999")
    second = await import_rows(test_session, changed, apply=True)
    assert all(r["action"] == "existing" for r in second)
    products = (await test_session.execute(select(CanonicalProduct.__table__))).mappings().all()
    assert len(products) == 5
    assert sorted(p["reference_price"] for p in products if p["reference_price"]) == [
        Decimal("40000"),
        Decimal("52000"),
        Decimal("54000"),
        Decimal("68000"),
    ]
    assert all(p["attributes"]["stock_unverified"] for p in products)
    assert all(p["source_ref"] == "sha256:" + rows[0].provenance["sha256"] for p in products)
    assert products[0]["attributes"]["catalog_import"]["sources"][0]["row"] == 2
    assert not (await test_session.execute(select(ShopProduct.id))).all()


async def test_existing_catalog_and_offer_are_preserved(
    test_session: AsyncSession, tmp_path: Path
) -> None:
    await references(test_session)
    path = workbook(
        tmp_path, "fanera.xlsx", [SHEET_HEADER, ["Fanera", "Rossiya", "2x4", "1525×1525", 3, 54000]]
    )
    rows, _ = read_workbook(path)
    async with test_session.begin():
        category_id = (
            await test_session.execute(
                select(Category.id).where(Category.slug == "plita-va-fanera")
            )
        ).scalar_one()
        product_id = (
            await test_session.execute(
                insert(CanonicalProduct)
                .values(
                    slug="fanera-bereza-2x4-3mm-1525x1525",
                    name_uz="Existing name",
                    name_uz_cyrl="Original",
                    name_ru="Original",
                    category_id=category_id,
                    base_unit_code="dona",
                    attributes={
                        "material": "birch_plywood",
                        "grade": "2x4",
                        "size": "1525x1525",
                        "thickness_mm": 3,
                        "detail": "keep me",
                    },
                    reference_price=Decimal("12345"),
                    source="supplier",
                    source_ref="fanera.uz",
                    is_active=False,
                    search_doc="original",
                )
                .returning(CanonicalProduct.id)
            )
        ).scalar_one()
        district_id = (
            await test_session.execute(
                insert(District).values(name_uz="test", name_ru="test").returning(District.id)
            )
        ).scalar_one()
        shop_id = (
            await test_session.execute(
                insert(Shop)
                .values(name="test", phone="test", district_id=district_id, address="test")
                .returning(Shop.id)
            )
        ).scalar_one()
        await test_session.execute(
            insert(ShopProduct).values(
                shop_id=shop_id,
                canonical_id=product_id,
                raw_name="original",
                raw_unit="dona",
                pack_size=1,
                price_per_pack=Decimal("76543"),
                price_per_base_unit=Decimal("76543"),
                stock_status="out",
                updated_by="admin",
            )
        )

    async def snapshot():
        async with test_session.begin():
            return [
                (await test_session.execute(select(table))).mappings().all()
                for table in (CanonicalProduct.__table__, ShopProduct.__table__)
            ]

    before = await snapshot()
    assert (await import_rows(test_session, rows, apply=True))[0]["action"] == "existing"
    assert await snapshot() == before


async def test_pack_and_grade_identity_and_conflicting_price_basis(
    test_session: AsyncSession, tmp_path: Path
) -> None:
    await references(test_session)
    path = workbook(
        tmp_path,
        "reka.xlsx",
        [
            ["Mahsulot nomi", "O'lcham", "Qadoq", "Umumioy o'lcham", "Sifat", "Narx (So’m/dona)"],
            ["Reka", "4x2", "пачка", "40 metr", "1 sort", 189000],
            ["Reka", "4x2", "пачка", "40 metr", "2 sort", 166000],
            ["Reka", "4x2", "пачка", "48 metr", "1 sort", 200000],
            ["Reka", "4x2", "dona", "40 metr", "1 sort", 189000],
        ],
    )
    rows, _ = read_workbook(path)
    assert len({r.key for r in rows}) == 4
    assert [r.reference_price for r in rows] == [None, None, None, Decimal("189000")]
    assert all(d["action"] == "add" for d in await import_rows(test_session, rows, apply=True))


async def test_failure_rolls_back_entire_batch(test_session: AsyncSession, tmp_path: Path) -> None:
    await references(test_session)
    path = workbook(
        tmp_path,
        "fanera.xlsx",
        [
            SHEET_HEADER,
            ["Fanera", "Rossiya", "2x4", "1525×1525", 3, 54000],
            ["Fanera", "Rossiya", "2x4", "1525×1525", 4, 68000],
        ],
    )
    rows, _ = read_workbook(path)
    rows[1].attributes["invalid_json"] = object()
    from sqlalchemy.exc import StatementError

    with pytest.raises(StatementError):
        await import_rows(test_session, rows, apply=True)
    assert not (await test_session.execute(select(CanonicalProduct.id))).all()
