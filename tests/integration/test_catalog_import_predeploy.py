"""Deploy seeding must not undo an approved add-only Excel import."""

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CanonicalProduct, ShopProduct, ShopProductPriceTier
from scripts import seed
from scripts.catalog_import import import_rows, read_workbook


async def test_import_before_seed_does_not_duplicate_variant_or_create_offer(
    test_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = next(
        item
        for item in seed.generate_catalog_data()
        if item.slug == "fanera-bereza-2x4-3mm-1525x1525"
    )
    monkeypatch.setattr(seed, "generate_catalog_data", lambda: [])
    monkeypatch.setattr(seed, "our_priced_rows", lambda: [])
    await seed.seed_database(test_session, catalog_only=True)
    await test_session.commit()
    book = Workbook()
    book.active.append(
        [
            "Mahsulot nomi",
            "Ishlab chiqaruvchi",
            "",
            "O'lcham (mm)",
            "Qalinlik (mm)",
            "Narx (So’m/dona)",
        ]
    )
    book.active.append(["Fanera", "Rossiya", "2x4", "1525×1525", 3, 54000])
    path = tmp_path / "fanera.xlsx"
    book.save(path)
    book.close()
    rows, _ = read_workbook(path)
    await import_rows(test_session, rows, apply=True)
    monkeypatch.setattr(seed, "generate_catalog_data", lambda: [item])
    monkeypatch.setattr(seed, "our_priced_rows", lambda: [(item.slug, "1", None, None)])
    await seed.seed_database(test_session, catalog_only=True)
    await test_session.commit()
    async with test_session.begin():
        products = (await test_session.execute(select(CanonicalProduct.__table__))).mappings().all()
        assert len(products) == 1
        assert products[0]["attributes"]["catalog_import"]["sources"][0]["row"] == 2
        assert products[0]["reference_price"] == Decimal("54000")
        assert not (await test_session.execute(select(ShopProduct.id))).all()


async def test_repeated_predeploy_preserves_import_and_operator_data(
    test_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    priced_slugs = {row[0] for row in seed.our_priced_rows()}
    catalog = [item for item in seed.generate_catalog_data() if item.slug in priced_slugs][:2]
    monkeypatch.setattr(seed, "generate_catalog_data", lambda: catalog)
    original_offers = seed.our_priced_rows()
    monkeypatch.setattr(
        seed,
        "our_priced_rows",
        lambda: [row for row in original_offers if row[0] in {item.slug for item in catalog}],
    )
    await seed.seed_database(test_session, catalog_only=True)
    await test_session.commit()

    book = Workbook()
    book.active.append(
        [
            "Mahsulot nomi",
            "Ishlab chiqaruvchi",
            "",
            "O'lcham (mm)",
            "Qalinlik (mm)",
            "Narx (So’m/dona)",
        ]
    )
    book.active.append(["DSP", "Rossiya (Kronospan)", "", "2750×1830", "16", 260000])
    path = tmp_path / "fanera.xlsx"
    book.save(path)
    book.close()
    rows, _ = read_workbook(path)
    assert (await import_rows(test_session, rows, apply=True))[0]["action"] == "add"

    async with test_session.begin():
        products = (
            (
                await test_session.execute(
                    select(CanonicalProduct)
                    .where(CanonicalProduct.slug.in_([item.slug for item in catalog]))
                    .order_by(CanonicalProduct.id)
                )
            )
            .scalars()
            .all()
        )
        products[0].reference_price = Decimal("777")
        products[0].attributes = {
            "catalog_import": {"sources": [{"row": 55}]},
            "price_on_request": True,
            "stock_unverified": True,
        }
        products[0].source_ref = "sha256:" + "a" * 64
        products[0].name_uz = "Operator details"
        products[0].is_active = False
        products[1].reference_price = None
        products[1].attributes = {"stock_unverified": True}
        offers = (
            (await test_session.execute(select(ShopProduct).order_by(ShopProduct.id)))
            .scalars()
            .all()
        )
        assert len(offers) == 2
        offers[0].price_per_pack = Decimal("888")
        offers[0].price_per_base_unit = Decimal("888")
        offers[0].stock_status = "out"
        offers[0].is_active = False
        offers[0].staleness_state = "stale"
        await test_session.execute(
            update(ShopProductPriceTier)
            .where(ShopProductPriceTier.shop_product_id == offers[0].id)
            .values(price_per_pack=Decimal("666"))
        )
        # Deliberately catalog-only: redeploy must not reconstruct this offer.
        await test_session.delete(offers[1])

    async def snapshot():
        async with test_session.begin():
            return [
                (await test_session.execute(select(model.__table__).order_by(model.id)))
                .mappings()
                .all()
                for model in (CanonicalProduct, ShopProduct, ShopProductPriceTier)
            ]

    before = await snapshot()
    for _ in range(2):
        await seed.seed_database(test_session, catalog_only=True)
        await test_session.commit()
        assert await snapshot() == before
    assert all(r["action"] == "existing" for r in await import_rows(test_session, rows))
