from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct, Category, ProductAlias, Unit
from app.db.repositories.base import BaseRepository


class CatalogRepository(BaseRepository[CanonicalProduct]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CanonicalProduct, session)

    async def get_unit(self, code: str) -> Unit | None:
        return await self.session.get(Unit, code)

    async def list_units(self) -> Sequence[Unit]:
        stmt = select(Unit).order_by(Unit.code)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_category(self, id: int) -> Category | None:
        return await self.session.get(Category, id)

    async def get_category_by_slug(self, slug: str) -> Category | None:
        stmt = select(Category).where(Category.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_root_categories(self) -> Sequence[Category]:
        stmt = select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort_order)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_canonical_by_slug(self, slug: str) -> CanonicalProduct | None:
        stmt = select(CanonicalProduct).where(CanonicalProduct.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_approved_alias(self, alias_norm: str) -> ProductAlias | None:
        stmt = select(ProductAlias).where(
            ProductAlias.alias_norm == alias_norm,
            ProductAlias.is_approved.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def record_alias_hit(self, alias_id: int) -> None:
        now = datetime.now(UTC)
        stmt = (
            update(ProductAlias)
            .where(ProductAlias.id == alias_id)
            .values(
                hit_count=ProductAlias.hit_count + 1,
                last_hit_at=now,
            )
        )
        await self.session.execute(stmt)

    async def search_canonical_products(
        self, query: str, limit: int = 20
    ) -> Sequence[CanonicalProduct]:
        """Fetch candidates for Stage 2 re-ranking using multi-token matching."""
        tokens = [t for t in query.split() if len(t) >= 2]
        if not tokens:
            stmt = select(CanonicalProduct).where(CanonicalProduct.is_active.is_(True)).limit(limit)
            result = await self.session.execute(stmt)
            return result.scalars().all()

        token_filters = [CanonicalProduct.search_doc.ilike(f"%{token}%") for token in tokens]
        stmt = (
            select(CanonicalProduct)
            .where(
                CanonicalProduct.is_active.is_(True),
                or_(*token_filters),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_unapproved_alias(
        self,
        canonical_id: int,
        alias_norm: str,
        alias_raw: str,
        confidence: float = 0.85,
        source: str = "llm",
    ) -> ProductAlias | None:
        """Self-learning feedback loop: write back alias for future fast lookups."""
        # Check if alias already exists
        stmt = select(ProductAlias).where(
            ProductAlias.canonical_id == canonical_id,
            ProductAlias.alias_norm == alias_norm,
        )
        res = await self.session.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return existing

        alias = ProductAlias(
            canonical_id=canonical_id,
            alias_norm=alias_norm,
            alias_raw=alias_raw,
            source=source,
            confidence=Decimal(str(round(confidence, 2))),
            is_approved=False,
        )
        self.session.add(alias)
        await self.session.flush()
        return alias

    # ─── Admin Panel Queries (§11) ─────────────────────────────────

    async def list_canonical_products(self, limit: int = 200) -> Sequence[CanonicalProduct]:
        stmt = (
            select(CanonicalProduct)
            .where(CanonicalProduct.is_active.is_(True))
            .order_by(CanonicalProduct.name_uz)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_canonical_product(
        self,
        slug: str,
        name_uz: str,
        name_uz_cyrl: str,
        name_ru: str,
        category_id: int,
        base_unit_code: str,
    ) -> CanonicalProduct:
        product = CanonicalProduct(
            slug=slug,
            name_uz=name_uz,
            name_uz_cyrl=name_uz_cyrl,
            name_ru=name_ru,
            category_id=category_id,
            base_unit_code=base_unit_code,
            search_doc=f"{name_uz} {name_uz_cyrl} {name_ru}".lower(),
        )
        self.session.add(product)
        await self.session.flush()
        return product

    async def create_approved_alias(
        self,
        canonical_id: int,
        alias_norm: str,
        alias_raw: str,
        source: str = "admin",
    ) -> ProductAlias:
        alias = ProductAlias(
            canonical_id=canonical_id,
            alias_norm=alias_norm,
            alias_raw=alias_raw,
            source=source,
            confidence=Decimal("1.00"),
            is_approved=True,
        )
        self.session.add(alias)
        await self.session.flush()
        return alias

    async def list_unapproved_aliases(self, limit: int = 100) -> Sequence[ProductAlias]:
        stmt = (
            select(ProductAlias)
            .where(ProductAlias.is_approved.is_(False))
            .order_by(ProductAlias.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def approve_alias(self, alias_id: int) -> None:
        stmt = update(ProductAlias).where(ProductAlias.id == alias_id).values(is_approved=True)
        await self.session.execute(stmt)

    async def reject_alias(self, alias_id: int) -> None:
        stmt = delete(ProductAlias).where(ProductAlias.id == alias_id)
        await self.session.execute(stmt)
