"""Integration tests for the supplier service — import pipeline.

Tests run against a real test DB with seeded data.
Key assertions:
1. Zero direct writes to shop_products before confirmation
2. price_history rows created on every price update
3. 150-row Excel imports end-to-end
4. Batch cancellation safety
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fx import FxRateSetting
from app.db.models.shop import District, PriceHistory, ShopProduct
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.services.supplier_service import SupplierService
from scripts.seed import seed_database


def _make_excel(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_supplier_import_full_pipeline(test_session: AsyncSession) -> None:
    """Full pipeline: upload → parse → stage → confirm → verify shop_products + price_history."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)
    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    # Create a small Excel file with known products
    file_bytes = _make_excel(
        headers=["Nomi", "Narxi", "Birlik"],
        rows=[
            ["Fanera berezovaya 3x3 12 mm", 155000, "dona"],
            ["OSB-3 plita 9 mm", 118000, "dona"],
            ["DVP plita 3.2 mm", 65000, "dona"],
        ],
    )

    # Count shop_products before
    count_before_stmt = (
        select(func.count()).select_from(ShopProduct).where(ShopProduct.shop_id == 1)
    )
    count_before_res = await test_session.execute(count_before_stmt)
    count_before = count_before_res.scalar() or 0

    # Process upload (staging only — no shop_products writes)
    summary = await svc.process_file_upload(
        shop_id=1,
        file_bytes=file_bytes,
        filename="test_prices.xlsx",
        source_currency="UZS",
    )
    await test_session.flush()

    assert summary.total_rows == 3
    assert summary.batch_id > 0

    # Verify: batch exists in awaiting_confirmation status
    batch = await shop_repo.get_import_batch(summary.batch_id)
    assert batch is not None
    assert batch.status == "awaiting_confirmation"

    # CRITICAL: Zero direct writes — shop_products count unchanged
    count_after_stage_res = await test_session.execute(count_before_stmt)
    count_after_stage = count_after_stage_res.scalar() or 0
    assert count_after_stage == count_before, "shop_products must NOT be modified during staging!"

    # Now apply the batch
    result = await svc.apply_batch(summary.batch_id)
    await test_session.flush()

    assert result.applied_count >= 1  # At least some rows matched and applied
    imported_offers = (
        await test_session.scalars(
            select(ShopProduct).where(ShopProduct.shop_id == 1, ShopProduct.updated_by == "import")
        )
    ).all()
    assert imported_offers
    assert all(offer.stock_qty is None for offer in imported_offers)

    # Verify batch marked as applied
    batch_after = await shop_repo.get_import_batch(summary.batch_id)
    assert batch_after is not None
    assert batch_after.status == "applied"


@pytest.mark.asyncio
async def test_supplier_import_price_history(test_session: AsyncSession) -> None:
    """Verify price_history rows are created on import."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)
    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    # Count price_history before
    ph_before_stmt = select(func.count()).select_from(PriceHistory)
    ph_before_res = await test_session.execute(ph_before_stmt)
    ph_before = ph_before_res.scalar() or 0

    file_bytes = _make_excel(
        headers=["Nomi", "Narxi"],
        rows=[["Fanera berezovaya 3x3 12 mm", 156000]],
    )

    summary = await svc.process_file_upload(
        shop_id=1, file_bytes=file_bytes, filename="prices.xlsx", source_currency="UZS"
    )
    await svc.apply_batch(summary.batch_id)
    await test_session.flush()

    # price_history should have grown
    ph_after_res = await test_session.execute(ph_before_stmt)
    ph_after = ph_after_res.scalar() or 0
    assert ph_after > ph_before, "price_history must be appended on import!"


@pytest.mark.asyncio
async def test_unlabelled_import_currency_blocks_the_whole_batch(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session)
    shop_repo = ShopRepository(test_session)
    svc = SupplierService(
        shop_repo,
        CatalogRepository(test_session),
        OpsRepository(test_session),
    )
    before = await test_session.scalar(
        select(func.count(ShopProduct.id)).where(ShopProduct.updated_by == "import")
    )
    file_bytes = _make_excel(
        headers=["Product Name", "Price", "Unit"],
        rows=[["Fanera berezovaya 3x3 12 mm", "155000", "dona"]],
    )

    summary = await svc.process_file_upload(
        shop_id=1,
        file_bytes=file_bytes,
        filename="unlabelled.xlsx",
    )
    result = await svc.apply_batch(summary.batch_id)

    after = await test_session.scalar(
        select(func.count(ShopProduct.id)).where(ShopProduct.updated_by == "import")
    )
    assert summary.currency_errors == 1
    assert result.currency_blocked is True
    assert result.applied_count == 0
    assert result.error_count == 1
    assert after == before


@pytest.mark.asyncio
async def test_import_currency_column_sets_usd_source_and_materialized_uzs(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session)
    test_session.add(FxRateSetting(id=1, usd_to_uzs_rate=Decimal("11820.48"), revision=1))
    await test_session.flush()
    svc = SupplierService(
        ShopRepository(test_session),
        CatalogRepository(test_session),
        OpsRepository(test_session),
    )
    file_bytes = _make_excel(
        headers=["Product Name", "Price", "Unit", "Currency"],
        rows=[["Fanera berezovaya 3x3 12 mm", "4.80", "dona", "USD"]],
    )

    summary = await svc.process_file_upload(
        shop_id=1,
        file_bytes=file_bytes,
        filename="usd_prices.xlsx",
    )
    result = await svc.apply_batch(summary.batch_id)
    offer = await test_session.scalar(
        select(ShopProduct).where(
            ShopProduct.shop_id == 1,
            ShopProduct.source_currency == "USD",
            ShopProduct.updated_by == "import",
        )
    )

    assert summary.currency_errors == 0
    assert result.applied_count == 1
    assert result.error_count == 0
    assert offer is not None
    assert offer.currency == "UZS"
    assert offer.source_price_per_pack == Decimal("4.8000")
    assert offer.price_per_pack == Decimal("56738.30")
    assert offer.fx_rate_used == Decimal("11820.480000")
    assert offer.fx_rate_revision == 1


@pytest.mark.asyncio
async def test_import_keeps_multiple_pack_variants_and_converts_base_unit_price(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session)
    catalog = CatalogRepository(test_session)
    canonical_name = "Fanera berezovaya 3x3 12 mm (1525x1525)"
    matches = await catalog.search_canonical_products(canonical_name, require_offers=False)
    canonical = next(product for product in matches if product.name_uz == canonical_name)
    existing = await test_session.scalar(
        select(ShopProduct).where(
            ShopProduct.shop_id == 1,
            ShopProduct.canonical_id == canonical.id,
            ShopProduct.pack_size == Decimal("1"),
            ShopProduct.pack_unit_code == "dona",
        )
    )
    if existing is None:
        existing = ShopProduct(
            shop_id=1,
            canonical_id=canonical.id,
            raw_name=canonical.name_uz,
            raw_unit="dona",
            pack_size=Decimal("1"),
            pack_unit_code="dona",
            price_per_pack=Decimal("58000"),
            price_per_base_unit=Decimal("58000"),
            currency="UZS",
            source_currency="UZS",
            source_price_per_pack=Decimal("58000"),
            fx_rate_used=Decimal("1"),
            fx_rate_revision=0,
            stock_status="in_stock",
            updated_by="admin",
        )
        test_session.add(existing)
    else:
        existing.price_per_pack = Decimal("58000")
        existing.price_per_base_unit = Decimal("58000")
        existing.source_currency = "UZS"
        existing.source_price_per_pack = Decimal("58000")
        existing.fx_rate_used = Decimal("1")
        existing.fx_rate_revision = 0
        existing.updated_by = "admin"
    await test_session.flush()
    existing_id = existing.id

    service = SupplierService(ShopRepository(test_session), catalog, OpsRepository(test_session))
    file_bytes = _make_excel(
        headers=["Product Name", "Price", "Unit", "Pack Size"],
        rows=[
            [canonical_name, "59000", "dona", "1"],
            [canonical_name, "100000", "dona", "10"],
        ],
    )
    summary = await service.process_file_upload(
        shop_id=1,
        file_bytes=file_bytes,
        filename="multiple_packs.xlsx",
        source_currency="UZS",
    )
    result = await service.apply_batch(summary.batch_id)
    await test_session.flush()

    assert result.applied_count == 2
    offers = (
        await test_session.scalars(
            select(ShopProduct)
            .where(ShopProduct.shop_id == 1, ShopProduct.canonical_id == canonical.id)
            .order_by(ShopProduct.pack_size)
        )
    ).all()
    by_pack = {offer.pack_size: offer for offer in offers}
    assert len(by_pack) == len(offers)
    assert by_pack[Decimal("1.0000")].id == existing_id
    assert by_pack[Decimal("1.0000")].price_per_pack == Decimal("59000.00")
    ten_pack = by_pack[Decimal("10.0000")]
    assert ten_pack.source_price_per_pack == Decimal("100000.0000")
    assert ten_pack.price_per_pack == Decimal("100000.00")
    assert ten_pack.price_per_base_unit == Decimal("10000.0000")


@pytest.mark.asyncio
async def test_supplier_import_batch_cancellation(test_session: AsyncSession) -> None:
    """Cancelled batch must NOT create any shop_products."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)
    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    count_before_stmt = (
        select(func.count()).select_from(ShopProduct).where(ShopProduct.shop_id == 1)
    )
    count_before_res = await test_session.execute(count_before_stmt)
    count_before = count_before_res.scalar() or 0

    file_bytes = _make_excel(
        headers=["Nomi", "Narxi"],
        rows=[["Fanera berezovaya 3x3 12 mm", 160000]],
    )

    summary = await svc.process_file_upload(
        shop_id=1, file_bytes=file_bytes, filename="cancel_test.xlsx"
    )
    await test_session.flush()

    # Cancel the batch
    await svc.cancel_batch(summary.batch_id)
    await test_session.flush()

    batch = await shop_repo.get_import_batch(summary.batch_id)
    assert batch is not None
    assert batch.status == "failed"

    # shop_products must be unchanged
    count_after_res = await test_session.execute(count_before_stmt)
    count_after = count_after_res.scalar() or 0
    assert count_after == count_before


@pytest.mark.asyncio
async def test_supplier_import_150_rows(test_session: AsyncSession) -> None:
    """SPEC deliverable: 150-row Excel imports with staging and confirmation."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)
    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    # Generate 150 rows with realistic product names
    product_names = [
        "Fanera berezovaya 3x3 12 mm",
        "Fanera berezovaya 3x3 18 mm",
        "OSB-3 plita 9 mm",
        "OSB-3 plita 12 mm",
        "DVP plita 3.2 mm",
        "HDF plita Kronospan 3.2 mm",
        "Fanera berezovaya 3x3 21 mm",
        "Fanera laminatsiyalangan SEGEZHA 18 mm",
        "Fanera berezovaya 2x4 9 mm",
        "Fanera berezovaya 4x4 4 mm",
    ]
    rows = []
    for i in range(150):
        name = product_names[i % len(product_names)]
        price = 10000 + i * 500
        rows.append([f"{name} #{i}", price, "dona"])

    file_bytes = _make_excel(
        headers=["Mahsulot nomi", "Narxi", "Birlik"],
        rows=rows,
    )

    summary = await svc.process_file_upload(
        shop_id=1, file_bytes=file_bytes, filename="150_rows.xlsx", source_currency="UZS"
    )
    await test_session.flush()

    assert summary.total_rows == 150
    assert summary.auto_matched + summary.needs_review == 150

    # Apply and verify
    result = await svc.apply_batch(summary.batch_id)
    await test_session.flush()

    assert result.applied_count + result.skipped_count + result.error_count == 150


@pytest.mark.asyncio
async def test_supplier_quick_price_with_history(test_session: AsyncSession) -> None:
    """Quick price update creates price_history entry."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)

    # Get an existing shop product
    stmt = select(ShopProduct).where(ShopProduct.shop_id == 1).limit(1)
    res = await test_session.execute(stmt)
    product = res.scalars().first()
    assert product is not None
    product.stock_qty = Decimal("12")  # Simulate a legacy quantity before price editing.
    await test_session.flush()

    # Count history before
    ph_stmt = (
        select(func.count())
        .select_from(PriceHistory)
        .where(PriceHistory.shop_product_id == product.id)
    )
    ph_before_res = await test_session.execute(ph_stmt)
    ph_before = ph_before_res.scalar() or 0

    # Update price
    new_price = Decimal("99999.00")
    await shop_repo.update_offer_price(
        shop_product_id=product.id,
        price_per_pack=new_price,
        price_per_base_unit=new_price,
        updated_by="shop",
    )
    await test_session.flush()

    # Verify price_history increased
    ph_after_res = await test_session.execute(ph_stmt)
    ph_after = ph_after_res.scalar() or 0
    assert ph_after == ph_before + 1

    # Verify product updated
    updated = await test_session.get(ShopProduct, product.id)
    assert updated is not None
    assert updated.price_per_pack == new_price
    assert updated.staleness_state == "fresh"
    assert updated.stock_qty is None
    assert updated.currency == "UZS"
    assert updated.source_currency == "UZS"
    assert updated.source_price_per_pack == new_price
    assert updated.fx_rate_used == Decimal("1")
    assert updated.fx_rate_revision == 0


@pytest.mark.asyncio
async def test_supplier_delivery_rule_upsert_preserves_province_customization(
    test_session: AsyncSession,
) -> None:
    """A regional house rule keeps its custom fee, threshold and minimum."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)
    province = District(
        region="Toshkent viloyati", name_uz="Test viloyati", name_ru="Тестовая область"
    )
    test_session.add(province)
    await test_session.flush()

    # Create new rule
    rule = await shop_repo.upsert_delivery_rule(
        shop_id=1,
        district_id=province.id,
        fee=Decimal("35000"),
        free_above=Decimal("500000"),
        min_order=Decimal("100000"),
        eta_hours=12,
    )
    await test_session.flush()
    assert rule.fee == Decimal("35000")
    assert rule.free_above == Decimal("500000")
    assert rule.min_order == Decimal("100000")

    # Update the same rule
    updated_rule = await shop_repo.upsert_delivery_rule(
        shop_id=1,
        district_id=province.id,
        fee=Decimal("40000"),
        free_above=Decimal("600000"),
        min_order=Decimal("150000"),
        eta_hours=8,
    )
    await test_session.flush()
    assert updated_rule.id == rule.id
    assert updated_rule.fee == Decimal("40000")
    assert updated_rule.free_above == Decimal("600000")
    assert updated_rule.min_order == Decimal("150000")
    assert updated_rule.eta_hours == 8
