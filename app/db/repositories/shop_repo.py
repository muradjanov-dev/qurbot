from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import OrderShopPart
from app.db.models.shop import (
    District,
    ImportBatch,
    ImportRow,
    PriceHistory,
    ProductPhotoBlob,
    Shop,
    ShopDeliveryRule,
    ShopOwner,
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
        """Find the shop this Telegram account manages.

        Checks the shop_owners join table as well as the legacy single
        Shop.owner_tg_id column, so shops created before multi-owner support
        (and anything seeded) keep resolving.
        """
        stmt = (
            select(Shop)
            .outerjoin(ShopOwner, ShopOwner.shop_id == Shop.id)
            .where(
                or_(
                    Shop.owner_tg_id == owner_tg_id,
                    and_(ShopOwner.tg_id == owner_tg_id, ShopOwner.is_active.is_(True)),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_shops_for_owner(self, owner_tg_id: int) -> Sequence[Shop]:
        """Every shop this account manages, newest last.

        One person commonly runs several branches, so this is the plural form
        of get_shop_by_owner_tg_id and honours both the shop_owners table and
        the legacy Shop.owner_tg_id column.
        """
        stmt = (
            select(Shop)
            .outerjoin(ShopOwner, ShopOwner.shop_id == Shop.id)
            .where(
                Shop.is_active.is_(True),
                or_(
                    Shop.owner_tg_id == owner_tg_id,
                    and_(ShopOwner.tg_id == owner_tg_id, ShopOwner.is_active.is_(True)),
                ),
            )
            .order_by(Shop.id)
            .distinct()
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_photo_for_canonical(self, canonical_id: int) -> tuple[str, bytes | None] | None:
        """A photo to show customers for this product, if any owner uploaded one.

        Returns (file_id, blob_bytes). The file_id is tried first because
        re-sending it costs no upload; the bytes are the fallback for when a
        file_id has expired, which happens whenever the bot token is rotated.
        """
        stmt = (
            select(ShopProduct)
            .where(
                ShopProduct.canonical_id == canonical_id,
                ShopProduct.is_active.is_(True),
                ShopProduct.moderation_status == "approved",
            )
            .order_by(ShopProduct.id)
        )
        result = await self.session.execute(stmt)
        for product in result.scalars().all():
            photos = product.photos or []
            if not photos:
                continue
            first = sorted(photos, key=lambda ph: ph.get("pos", 0))[0]
            file_id = str(first.get("file_id", ""))
            unique_id = first.get("file_unique_id")
            if not file_id:
                continue
            blob_bytes: bytes | None = None
            if unique_id:
                blob_stmt = select(ProductPhotoBlob).where(
                    ProductPhotoBlob.file_unique_id == str(unique_id)
                )
                blob = (await self.session.execute(blob_stmt)).scalars().first()
                blob_bytes = blob.data if blob else None
            return file_id, blob_bytes
        return None

    async def list_shop_owners(self, shop_id: int) -> Sequence[ShopOwner]:
        stmt = (
            select(ShopOwner)
            .where(ShopOwner.shop_id == shop_id, ShopOwner.is_active.is_(True))
            .order_by(ShopOwner.id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_shop_owner(
        self, shop_id: int, tg_id: int, full_name: str | None = None
    ) -> ShopOwner:
        stmt = select(ShopOwner).where(ShopOwner.shop_id == shop_id, ShopOwner.tg_id == tg_id)
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            existing.is_active = True
            if full_name:
                existing.full_name = full_name
            await self.session.flush()
            return existing

        owner = ShopOwner(shop_id=shop_id, tg_id=tg_id, full_name=full_name, is_active=True)
        self.session.add(owner)
        await self.session.flush()
        return owner

    async def remove_shop_owner(self, shop_id: int, tg_id: int) -> bool:
        stmt = select(ShopOwner).where(ShopOwner.shop_id == shop_id, ShopOwner.tg_id == tg_id)
        result = await self.session.execute(stmt)
        owner = result.scalars().first()
        if owner is None:
            return False
        owner.is_active = False
        await self.session.flush()
        return True

    async def create_shop(
        self,
        name: str,
        phone: str,
        district_id: int,
        address: str,
    ) -> Shop:
        shop = Shop(
            name=name,
            phone=phone,
            district_id=district_id,
            address=address,
            is_active=True,
        )
        self.session.add(shop)
        await self.session.flush()
        return shop

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

    # ─── Background Job Queries (§10) ──────────────────────────────

    async def count_stale_offers(self) -> int:
        stmt = select(func.count()).where(
            ShopProduct.is_active.is_(True),
            ShopProduct.staleness_state == "stale",
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_active_offers_updated_before(self, cutoff: datetime) -> Sequence[ShopProduct]:
        stmt = select(ShopProduct).where(
            ShopProduct.is_active.is_(True),
            ShopProduct.updated_at < cutoff,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def bulk_set_staleness(self, ids: Sequence[int], staleness_state: str) -> None:
        if not ids:
            return
        stmt = (
            update(ShopProduct)
            .where(ShopProduct.id.in_(ids))
            .values(staleness_state=staleness_state)
        )
        await self.session.execute(stmt)

    async def list_shops_with_aging_offers(self) -> Sequence[Shop]:
        stmt = (
            select(Shop)
            .join(ShopProduct, ShopProduct.shop_id == Shop.id)
            .where(
                ShopProduct.staleness_state == "aging",
                ShopProduct.is_active.is_(True),
                Shop.owner_tg_id.is_not(None),
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def compute_freshness_ratios(self) -> dict[int, Decimal]:
        """Fraction of each shop's active offers currently 'fresh', for trust scoring."""
        stmt = (
            select(
                ShopProduct.shop_id,
                func.sum(case((ShopProduct.staleness_state == "fresh", 1), else_=0)),
                func.count(),
            )
            .where(ShopProduct.is_active.is_(True))
            .group_by(ShopProduct.shop_id)
        )
        result = await self.session.execute(stmt)
        return {
            shop_id: Decimal(fresh_count) / Decimal(total)
            for shop_id, fresh_count, total in result.all()
            if total
        }

    async def compute_accept_rates(self, since: datetime) -> dict[int, Decimal]:
        """Accepted / (accepted+rejected+partial) per shop over a trailing window."""
        responded = ("accepted", "rejected", "partial")
        stmt = (
            select(
                OrderShopPart.shop_id,
                func.sum(case((OrderShopPart.shop_response == "accepted", 1), else_=0)),
                func.sum(case((OrderShopPart.shop_response.in_(responded), 1), else_=0)),
            )
            .where(OrderShopPart.created_at >= since)
            .group_by(OrderShopPart.shop_id)
        )
        result = await self.session.execute(stmt)
        return {
            shop_id: Decimal(accepted) / Decimal(total)
            for shop_id, accepted, total in result.all()
            if total
        }

    async def update_trust_score(self, shop_id: int, trust_score: Decimal) -> None:
        stmt = update(Shop).where(Shop.id == shop_id).values(trust_score=trust_score)
        await self.session.execute(stmt)

    # ─── Admin Panel Queries (§11) ─────────────────────────────────

    async def verify_shop(self, shop_id: int) -> None:
        stmt = update(Shop).where(Shop.id == shop_id).values(verified_at=datetime.now(UTC))
        await self.session.execute(stmt)

    async def set_shop_active(self, shop_id: int, is_active: bool) -> None:
        stmt = update(Shop).where(Shop.id == shop_id).values(is_active=is_active)
        await self.session.execute(stmt)

    async def list_offers_by_staleness(
        self, staleness_state: str | None = None, limit: int = 100
    ) -> Sequence[ShopProduct]:
        stmt = select(ShopProduct).order_by(ShopProduct.updated_at.asc()).limit(limit)
        if staleness_state:
            stmt = stmt.where(ShopProduct.staleness_state == staleness_state)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def bulk_deactivate_offers(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        stmt = update(ShopProduct).where(ShopProduct.id.in_(ids)).values(is_active=False)
        await self.session.execute(stmt)

    async def common_packs_for_canonical(
        self, canonical_id: int, limit: int = 3
    ) -> list[tuple[Decimal, str]]:
        """The pack sizes this product is most often sold in, commonest first.

        Used to offer a shop owner one-tap pack choices drawn from what the
        market actually uses, which keeps pack sizes consistent between shops --
        a prerequisite for the per-base-unit comparison to be like-for-like.
        """
        stmt = (
            select(
                ShopProduct.pack_size,
                ShopProduct.pack_unit_code,
                func.count().label("uses"),
            )
            .where(
                ShopProduct.canonical_id == canonical_id,
                ShopProduct.is_active.is_(True),
                ShopProduct.pack_unit_code.is_not(None),
            )
            .group_by(ShopProduct.pack_size, ShopProduct.pack_unit_code)
            .order_by(func.count().desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all() if row[1]]
