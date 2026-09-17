"""Shared live cart. Callers commit; every mutation is serialized on its cart row.

Quantities retain their unit (a bag must never silently become a kilogram).
No prices or stock are copied: quotes continue to use the existing live offers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainException
from app.db.models.cart import Cart, CartItem, CartMerge
from app.db.models.catalog import CanonicalProduct
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.domain.pricing.units import STANDARD_UNITS


class CartConflict(DomainException):
    def __init__(self, revision: int) -> None:
        super().__init__("cart_conflict")
        self.revision = revision


class InvalidCartItem(DomainException):
    pass


@dataclass(frozen=True)
class CartSnapshot:
    revision: int
    lines: tuple[dict[str, Any], ...]

    def payload(self) -> dict[str, Any]:
        return {"ok": True, "revision": self.revision, "lines": list(self.lines)}


class CartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _check_size(count: int) -> None:
        # Match the existing quote validator while older configuration objects
        # are still in use during the parent integration.
        if count > getattr(settings, "cart_max_lines", 60):
            raise InvalidCartItem("cart_too_large")

    async def lock(self, user_id: int) -> None:
        """Lock through the caller's commit, including first-cart creation races."""
        insert = sqlite_insert if self.session.get_bind().dialect.name == "sqlite" else pg_insert
        await self.session.execute(
            insert(Cart).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
        )
        await self.session.execute(
            update(Cart).where(Cart.user_id == user_id).values(revision=Cart.revision)
        )

    async def get(self, user_id: int) -> CartSnapshot:
        # Reading under the same lock makes revision + items one consistent snapshot.
        await self.lock(user_id)
        revision = await self.session.scalar(select(Cart.revision).where(Cart.user_id == user_id))
        rows = await self.session.execute(
            select(CartItem, CanonicalProduct)
            .join(CanonicalProduct, CanonicalProduct.id == CartItem.canonical_id)
            .where(CartItem.user_id == user_id)
            .order_by(CartItem.canonical_id)
            .execution_options(populate_existing=True)
        )
        lines = tuple(
            {
                "line_no": index,
                "canonical_id": item.canonical_id,
                "qty": format(item.qty.normalize(), "f"),
                "unit_code": item.unit_code,
                "parsed_name": product.name_uz,
                "canonical_name": product.name_uz,
                "raw_text": f"{item.qty} {item.unit_code} {product.name_uz}",
                "status": "ok",
                "candidates": [],
            }
            for index, (item, product) in enumerate(rows, start=1)
        )
        return CartSnapshot(revision=int(revision or 0), lines=lines)

    async def _check(self, user_id: int, expected_revision: int) -> CartSnapshot:
        snapshot = await self.get(user_id)
        if snapshot.revision != expected_revision:
            raise CartConflict(snapshot.revision)
        return snapshot

    async def _bump(self, user_id: int) -> CartSnapshot:
        await self.session.execute(
            update(Cart).where(Cart.user_id == user_id).values(revision=Cart.revision + 1)
        )
        await self.session.flush()
        snapshot = await self.get(user_id)
        tg_id = await self.session.scalar(select(User.tg_id).where(User.id == user_id))
        await OpsRepository(self.session).log_event(
            "test_cart_updated" if tg_id in settings.test_tg_ids else "cart_updated",
            user_id=user_id,
            props={"revision": snapshot.revision, "items": len(snapshot.lines)},
        )
        return snapshot

    async def _validate(
        self, product_id: object, raw_qty: object, unit_code: str | None
    ) -> tuple[Decimal, str]:
        if not isinstance(product_id, int) or isinstance(product_id, bool) or product_id <= 0:
            raise InvalidCartItem("invalid_product")
        try:
            qty = Decimal(str(raw_qty))
        except (InvalidOperation, ValueError):
            raise InvalidCartItem("invalid_qty") from None
        if (
            not qty.is_finite()
            or qty <= 0
            or qty > settings.basket_max_qty
            or qty != qty.quantize(Decimal("0.000001"))
        ):
            raise InvalidCartItem("invalid_qty")
        product = await self.session.get(CanonicalProduct, product_id)
        enabled = await CatalogRepository(self.session).enabled_category_ids()
        if (
            product is None
            or not product.is_active
            or (enabled is not None and product.category_id not in enabled)
        ):
            raise InvalidCartItem("invalid_product")
        unit = unit_code or product.base_unit_code
        if unit not in STANDARD_UNITS:
            raise InvalidCartItem("invalid_unit")
        return qty, unit

    async def set_item(
        self,
        user_id: int,
        product_id: int,
        qty: object,
        *,
        expected_revision: int,
        unit_code: str | None = None,
    ) -> CartSnapshot:
        if str(qty) == "0":
            return await self.remove_item(user_id, product_id, expected_revision=expected_revision)
        snapshot = await self._check(user_id, expected_revision)
        quantity, unit = await self._validate(product_id, qty, unit_code)
        item = await self.session.get(CartItem, (user_id, product_id))
        if item is not None and item.qty == quantity and item.unit_code == unit:
            return snapshot
        if item is None:
            self._check_size(len(snapshot.lines) + 1)
            self.session.add(
                CartItem(user_id=user_id, canonical_id=product_id, qty=quantity, unit_code=unit)
            )
        else:
            item.qty, item.unit_code = quantity, unit
        return await self._bump(user_id)

    async def remove_item(
        self, user_id: int, product_id: int, *, expected_revision: int
    ) -> CartSnapshot:
        snapshot = await self._check(user_id, expected_revision)
        if not any(line["canonical_id"] == product_id for line in snapshot.lines):
            return snapshot
        await self.session.execute(
            delete(CartItem).where(CartItem.user_id == user_id, CartItem.canonical_id == product_id)
        )
        return await self._bump(user_id)

    async def clear(self, user_id: int, *, expected_revision: int) -> CartSnapshot:
        snapshot = await self._check(user_id, expected_revision)
        if not snapshot.lines:
            return snapshot
        await self.session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        return await self._bump(user_id)

    async def merge(
        self,
        user_id: int,
        lines: Sequence[dict[str, Any]],
        *,
        merge_key: str,
        expected_revision: int,
    ) -> CartSnapshot:
        snapshot = await self.get(user_id)
        if not merge_key or len(merge_key) > 160:
            raise InvalidCartItem("invalid_merge_key")
        # Receipts are checked before the revision: a lost-response retry succeeds.
        if await self.session.get(CartMerge, (user_id, merge_key)) is not None:
            return snapshot
        if snapshot.revision != expected_revision:
            raise CartConflict(snapshot.revision)
        merged = {line["canonical_id"]: dict(line) for line in snapshot.lines}
        for line in lines:
            product_id = line.get("canonical_id")
            if not isinstance(product_id, int) or isinstance(product_id, bool):
                raise InvalidCartItem("invalid_product")
            qty, unit = await self._validate(product_id, line.get("qty"), line.get("unit_code"))
            old = merged.get(product_id)
            if old is not None:
                if old["unit_code"] != unit:
                    raise InvalidCartItem("unit_conflict")
                qty = max(qty, Decimal(old["qty"]))
            merged[product_id] = {"canonical_id": product_id, "qty": str(qty), "unit_code": unit}
        # Validate the entire merge before making changes.
        self._check_size(len(merged))
        changed = False
        for product_id, line in merged.items():
            item = await self.session.get(CartItem, (user_id, product_id))
            if item is None:
                changed = True
                self.session.add(
                    CartItem(
                        user_id=user_id,
                        canonical_id=product_id,
                        qty=Decimal(line["qty"]),
                        unit_code=line["unit_code"],
                    )
                )
            else:
                changed = changed or item.qty != Decimal(line["qty"])
                item.qty = Decimal(line["qty"])
        self.session.add(CartMerge(user_id=user_id, merge_key=merge_key))
        if changed:
            return await self._bump(user_id)
        await self.session.flush()
        return snapshot

    async def migrate_legacy(self, user_id: int, data: dict[str, Any]) -> CartSnapshot:
        """Import each old storage source once; clearing FSM cannot reset receipts."""
        snapshot = await self.get(user_id)
        agent = data.get("agent")
        sources = {
            "fsm": data.get("basket_lines", []),
            "agent": agent.get("basket", []) if isinstance(agent, dict) else [],
        }
        for source, lines in sources.items():
            key = f"legacy:{source}:v1"
            if await self.session.get(CartMerge, (user_id, key)) is not None:
                continue
            valid = []
            units = {line["canonical_id"]: line["unit_code"] for line in snapshot.lines}
            if not isinstance(lines, list):
                lines = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                try:
                    _, unit = await self._validate(
                        line.get("canonical_id"), line.get("qty"), line.get("unit_code")
                    )
                except InvalidCartItem:
                    continue
                product_id = line["canonical_id"]
                if product_id in units and units[product_id] != unit:
                    continue
                units[product_id] = unit
                valid.append({**line, "unit_code": unit})
            snapshot = await self.merge(
                user_id, valid, merge_key=key, expected_revision=snapshot.revision
            )
        return snapshot
