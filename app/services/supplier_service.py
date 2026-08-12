"""Supplier service — orchestrates Excel/CSV import pipeline.

Pipeline: file parse → catalog match → stage in import_batches/import_rows
→ user confirmation → apply to shop_products + price_history.

Key invariant: ZERO direct writes to shop_products before confirmation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.parsing.excel_parser import (
    ImportRowData,
    parse_csv,
    parse_excel,
)
from app.services.catalog_service import CatalogService

logger = logging.getLogger(__name__)


@dataclass
class BatchSummary:
    """Summary of an import batch for confirmation UI."""

    batch_id: int
    total_rows: int
    auto_matched: int
    needs_review: int
    skipped: int
    filename: str


@dataclass
class ApplyResult:
    """Result of applying a confirmed batch."""

    applied_count: int
    skipped_count: int
    error_count: int


class SupplierService:
    """Orchestrates the supplier price file import pipeline."""

    def __init__(
        self,
        shop_repo: ShopRepository,
        catalog_repo: CatalogRepository,
        ops_repo: OpsRepository,
    ) -> None:
        self.shop_repo = shop_repo
        self.catalog_repo = catalog_repo
        self.ops_repo = ops_repo

    async def process_file_upload(
        self,
        shop_id: int,
        file_bytes: bytes,
        filename: str,
    ) -> BatchSummary:
        """Parse a file, match rows against catalog, and stage in import_batches.

        Returns a BatchSummary for the confirmation UI.
        NO writes to shop_products happen here.
        """
        # 1. Parse file in a thread (openpyxl is blocking I/O)
        lower_name = filename.lower()
        if lower_name.endswith((".xlsx", ".xls")):
            parsed = await asyncio.to_thread(parse_excel, file_bytes)
        elif lower_name.endswith(".csv"):
            parsed = await asyncio.to_thread(parse_csv, file_bytes)
        else:
            # Try Excel first, fall back to CSV
            parsed = await asyncio.to_thread(parse_excel, file_bytes)
            if not parsed.rows:
                parsed = await asyncio.to_thread(parse_csv, file_bytes)

        # 2. Create import batch
        batch = await self.shop_repo.create_import_batch(
            shop_id=shop_id,
            filename=filename,
            total_rows=parsed.total_rows,
        )

        # 3. Match each row against catalog
        catalog_service = CatalogService(self.catalog_repo, self.ops_repo)
        import_row_dicts: list[dict[str, object]] = []
        auto_count = 0
        needs_review = 0

        for row_data in parsed.rows:
            matched_id, confidence, resolution = await self._match_row(row_data, catalog_service)

            raw_payload = {
                "raw_name": row_data.raw_name,
                "raw_unit": row_data.raw_unit,
                "raw_price": str(row_data.raw_price) if row_data.raw_price else None,
                "raw_pack_size": str(row_data.raw_pack_size) if row_data.raw_pack_size else None,
            }

            import_row_dicts.append(
                {
                    "row_no": row_data.row_no,
                    "raw_payload": raw_payload,
                    "matched_canonical_id": matched_id,
                    "match_confidence": confidence,
                    "resolution": resolution,
                }
            )

            if resolution == "auto":
                auto_count += 1
            else:
                needs_review += 1

        # 4. Stage rows in DB
        await self.shop_repo.create_import_rows(batch.id, import_row_dicts)
        batch.matched_rows = auto_count
        await self.shop_repo.update_batch_status(batch.id, "awaiting_confirmation")

        logger.info(
            "Import batch %d: %d rows, %d auto-matched, %d need review",
            batch.id,
            parsed.total_rows,
            auto_count,
            needs_review,
        )

        return BatchSummary(
            batch_id=batch.id,
            total_rows=len(parsed.rows),
            auto_matched=auto_count,
            needs_review=needs_review,
            skipped=parsed.skipped_rows,
            filename=filename,
        )

    async def _match_row(
        self,
        row: ImportRowData,
        catalog_service: CatalogService,
    ) -> tuple[int | None, Decimal | None, str]:
        """Match a single import row against the catalog.

        Returns (canonical_id, confidence, resolution).
        """
        try:
            results = await catalog_service.parse_and_match_basket(row.raw_name)
            if not results:
                return None, None, "manual"

            _, decision = results[0]
            conf_decimal = Decimal(str(round(decision.confidence, 2)))
            if decision.canonical_id and decision.confidence >= 0.82:
                return (
                    decision.canonical_id,
                    conf_decimal,
                    "auto",
                )
            if decision.candidates:
                return (
                    decision.candidates[0].canonical_id,
                    conf_decimal,
                    "manual",
                )
            return None, None, "manual"
        except Exception:
            logger.exception("Error matching row %d: %s", row.row_no, row.raw_name)
            return None, None, "manual"

    async def get_batch_summary(self, batch_id: int) -> BatchSummary | None:
        """Load batch summary from DB."""
        batch = await self.shop_repo.get_import_batch(batch_id)
        if not batch:
            return None

        rows = await self.shop_repo.get_import_rows(batch_id)
        auto_count = sum(1 for r in rows if r.resolution == "auto" and r.matched_canonical_id)
        manual_count = sum(
            1 for r in rows if r.matched_canonical_id is None and r.resolution != "skipped"
        )
        skipped_count = sum(1 for r in rows if r.resolution == "skipped")

        return BatchSummary(
            batch_id=batch.id,
            total_rows=len(rows),
            auto_matched=auto_count,
            needs_review=manual_count,
            skipped=skipped_count,
            filename=batch.filename,
        )

    async def resolve_row(self, row_id: int, canonical_id: int) -> None:
        """Manually assign a canonical product to an import row."""
        await self.shop_repo.update_import_row_resolution(
            row_id=row_id,
            canonical_id=canonical_id,
            confidence=Decimal("1.00"),
            resolution="manual",
        )

    async def skip_row(self, row_id: int) -> None:
        """Mark an import row as skipped."""
        await self.shop_repo.update_import_row_resolution(
            row_id=row_id,
            canonical_id=None,
            confidence=None,
            resolution="skipped",
        )

    async def apply_batch(self, batch_id: int) -> ApplyResult:
        """Apply all matched rows in a batch to shop_products + price_history.

        This is the ONLY place where import data gets written to shop_products.
        """
        batch = await self.shop_repo.get_import_batch(batch_id)
        if not batch:
            return ApplyResult(applied_count=0, skipped_count=0, error_count=0)

        rows = await self.shop_repo.get_import_rows(batch_id)

        applied = 0
        skipped = 0
        errors = 0

        for row in rows:
            if not row.matched_canonical_id:
                skipped += 1
                continue

            if row.resolution == "skipped":
                skipped += 1
                continue

            payload = row.raw_payload
            raw_price_str = payload.get("raw_price")
            if not raw_price_str:
                skipped += 1
                continue

            try:
                price = Decimal(str(raw_price_str))
                pack_size = (
                    Decimal(str(payload["raw_pack_size"]))
                    if payload.get("raw_pack_size")
                    else Decimal("1")
                )
                raw_unit = str(payload.get("raw_unit") or "dona")

                await self.shop_repo.upsert_shop_product(
                    shop_id=batch.shop_id,
                    canonical_id=row.matched_canonical_id,
                    raw_name=str(payload.get("raw_name", "")),
                    price_per_pack=price,
                    pack_size=pack_size,
                    pack_unit_code=raw_unit,
                    raw_unit=raw_unit,
                    updated_by="import",
                )
                row.applied_shop_product_id = row.matched_canonical_id
                applied += 1
            except Exception:
                logger.exception("Error applying import row %d (batch %d)", row.row_no, batch_id)
                errors += 1

        await self.shop_repo.update_batch_status(batch_id, "applied")
        logger.info(
            "Applied batch %d: %d applied, %d skipped, %d errors",
            batch_id,
            applied,
            skipped,
            errors,
        )
        return ApplyResult(applied_count=applied, skipped_count=skipped, error_count=errors)

    async def cancel_batch(self, batch_id: int) -> None:
        """Cancel an import batch — no shop_products written."""
        await self.shop_repo.update_batch_status(batch_id, "failed")
