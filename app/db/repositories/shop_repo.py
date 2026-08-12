from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shop import (
    District,
    ImportBatch,
    ImportRow,
    PriceHistory,
    Shop,
    ShopDeliveryRule,
    ShopProduct,
)
from app.db.repositories.base import BaseRepository


class ShopRepository(BaseRepository[Shop]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Shop, session)

    async def get_district(self, id: int) -> District | None:
        return await self.session.get(District, id)

    async def list_districts(self) -> Sequence[District]:
        stmt = select(District).order_by(District.name_uz)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active_shops(self) -> Sequence[Shop]:
        stmt = select(Shop).where(Shop.is_active.is_(True)).order_by(Shop.name)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_shop_by_owner_tg_id(self, owner_tg_id: int) -> Shop | None:
        stmt = select(Shop).where(Shop.owner_tg_id == owner_tg_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_delivery_rule_for_district(
        self, shop_id: int, district_id: int | None
    ) -> ShopDeliveryRule | None:
        # Resolve most specific district match first,
        # fallback to district_id is None (all districts)
        if district_id is not None:
            stmt = select(ShopDeliveryRule).where(
                ShopDeliveryRule.shop_id == shop_id,
                ShopDeliveryRule.district_id == district_id,
            )
            result = await self.session.execute(stmt)
            rule = result.scalars().first()
            if rule:
                return rule

        fallback_stmt = select(ShopDeliveryRule).where(
            ShopDeliveryRule.shop_id == shop_id,
            ShopDeliveryRule.district_id.is_(None),
        )
        fallback_result = await self.session.execute(fallback_stmt)
        return fallback_result.scalars().first()

    async def get_active_offers_for_canonicals(
        self, canonical_ids: Sequence[int]
    ) -> Sequence[ShopProduct]:
        if not canonical_ids:
            return []
        stmt = (
            select(ShopProduct)
            .where(
                ShopProduct.canonical_id.in_(canonical_ids),
                ShopProduct.is_active.is_(True),
                ShopProduct.staleness_state != "stale",
                ShopProduct.stock_status.in_(["in_stock", "low", "on_order"]),
            )
            .order_by(ShopProduct.canonical_id, ShopProduct.price_per_base_unit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_delivery_rules_for_shops(
        self, shop_ids: Sequence[int], district_id: int | None = None
    ) -> dict[int, ShopDeliveryRule]:
        if not shop_ids:
            return {}
        stmt = select(ShopDeliveryRule).where(ShopDeliveryRule.shop_id.in_(shop_ids))
        result = await self.session.execute(stmt)
        rules = result.scalars().all()

        # Map each shop_id to its most specific rule
        rule_map: dict[int, ShopDeliveryRule] = {}
        for r in rules:
            if (district_id is not None and r.district_id == district_id) or (
                r.shop_id not in rule_map and r.district_id is None
            ):
                rule_map[r.shop_id] = r

        return rule_map

    async def update_offer_price(
        self,
        shop_product_id: int,
        price_per_pack: Decimal,
        price_per_base_unit: Decimal,
        updated_by: str = "shop",
    ) -> ShopProduct | None:
        product = await self.session.get(ShopProduct, shop_product_id)
        if not product:
            return None

        product.price_per_pack = price_per_pack
        product.price_per_base_unit = price_per_base_unit
        product.updated_by = updated_by
        product.staleness_state = "fresh"
        product.updated_at = datetime.now(UTC)

        history = PriceHistory(
            shop_product_id=shop_product_id,
            price_per_pack=price_per_pack,
            price_per_base_unit=price_per_base_unit,
        )
        self.session.add(history)
        await self.session.flush()
        return product

    # ─── Import Batch Methods ──────────────────────────────────────

    async def create_import_batch(
        self, shop_id: int, filename: str, total_rows: int
    ) -> ImportBatch:
        batch = ImportBatch(
            shop_id=shop_id,
            filename=filename,
            total_rows=total_rows,
            status="uploaded",
        )
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def create_import_rows(
        self, batch_id: int, rows: list[dict[str, Any]]
    ) -> list[ImportRow]:
        import_rows: list[ImportRow] = []
        for row_data in rows:
            ir = ImportRow(
                batch_id=batch_id,
                row_no=row_data["row_no"],
                raw_payload=row_data.get("raw_payload", {}),
                matched_canonical_id=row_data.get("matched_canonical_id"),
                match_confidence=row_data.get("match_confidence"),
                resolution=row_data.get("resolution", "auto"),
            )
            self.session.add(ir)
            import_rows.append(ir)
        await self.session.flush()
        return import_rows

    async def get_import_batch(self, batch_id: int) -> ImportBatch | None:
        return await self.session.get(ImportBatch, batch_id)

    async def get_import_rows(self, batch_id: int) -> Sequence[ImportRow]:
        stmt = select(ImportRow).where(ImportRow.batch_id == batch_id).order_by(ImportRow.row_no)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_unmatched_import_rows(self, batch_id: int) -> Sequence[ImportRow]:
        stmt = (
            select(ImportRow)
            .where(
                ImportRow.batch_id == batch_id,
                ImportRow.matched_canonical_id.is_(None),
                ImportRow.resolution != "skipped",
            )
            .order_by(ImportRow.row_no)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_import_row_resolution(
        self,
        row_id: int,
        canonical_id: int | None,
        confidence: Decimal | None = None,
        resolution: str = "manual",
    ) -> None:
        row = await self.session.get(ImportRow, row_id)
        if row:
            row.matched_canonical_id = canonical_id
            row.match_confidence = confidence
            row.resolution = resolution
            await self.session.flush()

    async def update_batch_status(self, batch_id: int, status: str) -> None:
        batch = await self.session.get(ImportBatch, batch_id)
        if batch:
            batch.status = status
            if status == "applied":
                batch.applied_at = datetime.now(UTC)
            await self.session.flush()

    # ─── Product Pagination ────────────────────────────────────────

    async def get_shop_products_paginated(
        self, shop_id: int, offset: int = 0, limit: int = 10
    ) -> tuple[Sequence[ShopProduct], int]:
        count_stmt = (
            select(func.count())
            .select_from(ShopProduct)
            .where(ShopProduct.shop_id == shop_id, ShopProduct.is_active.is_(True))
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        stmt = (
            select(ShopProduct)
            .where(ShopProduct.shop_id == shop_id, ShopProduct.is_active.is_(True))
            .order_by(ShopProduct.raw_name)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        products = result.scalars().all()
        return products, total

    # ─── Upsert Shop Product ──────────────────────────────────────

    async def upsert_shop_product(
        self,
        shop_id: int,
        canonical_id: int,
        raw_name: str,
        price_per_pack: Decimal,
        pack_size: Decimal = Decimal("1"),
        pack_unit_code: str = "dona",
        raw_unit: str = "dona",
        stock_status: str = "in_stock",
        updated_by: str = "import",
    ) -> ShopProduct:
        """Insert or update a shop product, always appending to price_history."""
        price_per_base = price_per_pack / pack_size if pack_size > Decimal("0") else price_per_pack

        stmt = select(ShopProduct).where(
            ShopProduct.shop_id == shop_id,
            ShopProduct.canonical_id == canonical_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()

        if existing:
            existing.price_per_pack = price_per_pack
            existing.price_per_base_unit = price_per_base
            existing.staleness_state = "fresh"
            existing.updated_by = updated_by
            existing.updated_at = datetime.now(UTC)
            existing.stock_status = stock_status

            history = PriceHistory(
                shop_product_id=existing.id,
                price_per_pack=price_per_pack,
                price_per_base_unit=price_per_base,
            )
            self.session.add(history)
            await self.session.flush()
            return existing

        product = ShopProduct(
            shop_id=shop_id,
            canonical_id=canonical_id,
            raw_name=raw_name,
            raw_unit=raw_unit,
            pack_size=pack_size,
            pack_unit_code=pack_unit_code,
            price_per_pack=price_per_pack,
            price_per_base_unit=price_per_base,
            currency="UZS",
            stock_status=stock_status,
            min_qty=Decimal("1"),
            is_active=True,
            staleness_state="fresh",
            updated_by=updated_by,
        )
        self.session.add(product)
        await self.session.flush()

        history = PriceHistory(
            shop_product_id=product.id,
            price_per_pack=price_per_pack,
            price_per_base_unit=price_per_base,
        )
        self.session.add(history)
        await self.session.flush()
        return product

    # ─── Delivery Rule Methods ─────────────────────────────────────

    async def get_shop_delivery_rules(self, shop_id: int) -> Sequence[ShopDeliveryRule]:
        stmt = (
            select(ShopDeliveryRule)
            .where(ShopDeliveryRule.shop_id == shop_id)
            .order_by(ShopDeliveryRule.district_id.nullslast())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert_delivery_rule(
        self,
        shop_id: int,
        district_id: int | None,
        fee: Decimal,
        free_above: Decimal | None = None,
        min_order: Decimal = Decimal("0"),
        eta_hours: int = 24,
    ) -> ShopDeliveryRule:
        if district_id is not None:
            stmt = select(ShopDeliveryRule).where(
                ShopDeliveryRule.shop_id == shop_id,
                ShopDeliveryRule.district_id == district_id,
            )
        else:
            stmt = select(ShopDeliveryRule).where(
                ShopDeliveryRule.shop_id == shop_id,
                ShopDeliveryRule.district_id.is_(None),
            )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()

        if existing:
            existing.fee = fee
            existing.free_above = free_above
            existing.min_order = min_order
            existing.eta_hours = eta_hours
            await self.session.flush()
            return existing

        rule = ShopDeliveryRule(
            shop_id=shop_id,
            district_id=district_id,
            fee=fee,
            free_above=free_above,
            min_order=min_order,
            eta_hours=eta_hours,
        )
        self.session.add(rule)
        await self.session.flush()
        return rule
