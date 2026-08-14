from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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

    async def list_child_categories(self, parent_id: int) -> Sequence[Category]:
        stmt = select(Category).where(Category.parent_id == parent_id).order_by(Category.sort_order)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_category_subtree_ids(self, category_id: int) -> list[int]:
        """Ids of a category and everything under it.

        The tree is capped at depth 3 (SPEC §4.1), so this walks level by level
        instead of using a recursive CTE -- at most two extra round trips, and
        it works identically on SQLite in tests.
        """
        collected = [category_id]
        frontier = [category_id]
        for _ in range(2):
            if not frontier:
                break
            stmt = select(Category.id).where(Category.parent_id.in_(frontier))
            result = await self.session.execute(stmt)
            frontier = [row for row in result.scalars().all()]
            collected.extend(frontier)
        return collected

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
        self,
        query: str,
        limit: int = 20,
        category_ids: Sequence[int] | None = None,
    ) -> Sequence[CanonicalProduct]:
        """Fetch candidates for Stage 2 re-ranking using multi-token matching.

        `category_ids` narrows the pool before the LIMIT is applied. That matters:
        the token filter is unranked, so without narrowing, a common token can
        fill the whole limit with rows from unrelated categories and push the
        real match out of the candidate set entirely. When the shop owner has
        already told us the category, using it is a straight precision win.
        """
        base_filters = [CanonicalProduct.is_active.is_(True)]
        if category_ids:
            base_filters.append(CanonicalProduct.category_id.in_(list(category_ids)))

        tokens = [t for t in query.split() if len(t) >= 2]
        if not tokens:
            stmt = select(CanonicalProduct).where(*base_filters).limit(limit)
            result = await self.session.execute(stmt)
            return result.scalars().all()

        token_filters = [CanonicalProduct.search_doc.ilike(f"%{token}%") for token in tokens]
        stmt = select(CanonicalProduct).where(*base_filters, or_(*token_filters)).limit(limit)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if rows:
            return rows

        # Substring matching finds nothing for a misspelling that shares no
        # whole token with the catalog ("paner" vs "fanera", "smnt" vs
        # "sement"). SPEC §6 Stage 2 specifies pg_trgm similarity for exactly
        # this; falling back to it here keeps those queries inside the pipeline
        # instead of reaching Stage 4 with an empty candidate list -- which also
        # meant Stage 3 (LLM) was skipped entirely, since it requires candidates.
        return await self._search_by_trigram_similarity(query, limit, category_ids)

    async def _search_by_trigram_similarity(
        self,
        query: str,
        limit: int,
        category_ids: Sequence[int] | None = None,
    ) -> Sequence[CanonicalProduct]:
        """Fuzzy candidate lookup via pg_trgm. No-op on non-PostgreSQL."""
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return []

        sim = func.similarity(CanonicalProduct.search_doc, query)
        filters = [CanonicalProduct.is_active.is_(True), sim > settings.match_trigram_threshold]
        if category_ids:
            filters.append(CanonicalProduct.category_id.in_(list(category_ids)))

        stmt = select(CanonicalProduct).where(*filters).order_by(sim.desc()).limit(limit)
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
