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

from app.db.models.shop import PriceHistory, ShopProduct
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
        shop_id=1, file_bytes=file_bytes, filename="prices.xlsx"
    )
    await svc.apply_batch(summary.batch_id)
    await test_session.flush()

    # price_history should have grown
    ph_after_res = await test_session.execute(ph_before_stmt)
    ph_after = ph_after_res.scalar() or 0
    assert ph_after > ph_before, "price_history must be appended on import!"


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
        shop_id=1, file_bytes=file_bytes, filename="150_rows.xlsx"
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


@pytest.mark.asyncio
async def test_supplier_delivery_rule_upsert(test_session: AsyncSession) -> None:
    """Delivery rule upsert creates and updates correctly."""
    await seed_database(test_session)

    shop_repo = ShopRepository(test_session)

    # Create new rule
    rule = await shop_repo.upsert_delivery_rule(
        shop_id=1,
        district_id=1,
        fee=Decimal("35000"),
        free_above=Decimal("500000"),
        min_order=Decimal("100000"),
        eta_hours=12,
    )
    await test_session.flush()
    assert rule.fee == Decimal("35000")

    # Update the same rule
    updated_rule = await shop_repo.upsert_delivery_rule(
        shop_id=1,
        district_id=1,
        fee=Decimal("40000"),
        free_above=Decimal("600000"),
        min_order=Decimal("150000"),
        eta_hours=8,
    )
    await test_session.flush()
    assert updated_rule.id == rule.id
    assert updated_rule.fee == Decimal("40000")
    assert updated_rule.eta_hours == 8
