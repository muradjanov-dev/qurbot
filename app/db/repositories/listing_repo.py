"""Persistence for in-progress listings and the photo bytes behind them.

Everything here exists so that an upload in progress survives things the bot
process cannot control -- a redeploy, a Redis eviction, a user who walks away
for two days. The wizard writes through this repository after every answer.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shop import ProductPhotoBlob, ShopProduct, ShopProductDraft
from app.domain.listing import ListingDraft, ListingStep, PhotoRef


def draft_to_domain(row: ShopProductDraft) -> ListingDraft:
    """Map a stored row onto the pure domain draft used for validation/resume."""
    photos = tuple(
        PhotoRef(
            file_id=str(p.get("file_id", "")),
            file_unique_id=str(p.get("file_unique_id", "")),
            pos=int(p.get("pos", idx)),
        )
        for idx, p in enumerate(row.photos or [])
    )
    visited: set[ListingStep] = set()
    for raw in row.visited_steps or []:
        try:
            visited.add(ListingStep(raw))
        except ValueError:
            # An unknown step name means the row predates a wizard change.
            # Ignoring it re-asks that question rather than losing the draft.
            continue
    return ListingDraft(
        category_id=row.category_id,
        name=row.name or "",
        description=row.description,
        pack_size=row.pack_size,
        pack_unit=row.pack_unit_code,
        price_per_pack=row.price_per_pack,
        stock_qty=row.stock_qty,
        photos=photos,
        visited_steps=frozenset(visited),
    )


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── drafts ────────────────────────────────────────────────────────────

    async def get_draft(self, draft_id: int) -> ShopProductDraft | None:
        return await self.session.get(ShopProductDraft, draft_id)

    async def get_open_draft(self, owner_tg_id: int) -> ShopProductDraft | None:
        """The owner's resumable draft, if any."""
        stmt = (
            select(ShopProductDraft)
            .where(
                ShopProductDraft.owner_tg_id == owner_tg_id,
                ShopProductDraft.status == "draft",
            )
            .order_by(ShopProductDraft.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_draft(self, shop_id: int, owner_tg_id: int) -> ShopProductDraft:
        draft = ShopProductDraft(
            shop_id=shop_id,
            owner_tg_id=owner_tg_id,
            status="draft",
            name="",
            photos=[],
            visited_steps=[],
        )
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def update_draft(self, draft: ShopProductDraft, **fields: Any) -> ShopProductDraft:
        for key, value in fields.items():
            setattr(draft, key, value)
        await self.session.flush()
        return draft

    async def mark_step_visited(
        self, draft: ShopProductDraft, step: ListingStep
    ) -> ShopProductDraft:
        visited = list(draft.visited_steps or [])
        if step.value not in visited:
            visited.append(step.value)
            # Reassign rather than mutate: a JSON column tracks changes by
            # identity, so an in-place append would not be flushed.
            draft.visited_steps = visited
        await self.session.flush()
        return draft

    async def append_photo(self, draft: ShopProductDraft, photo: PhotoRef) -> ShopProductDraft:
        photos = list(draft.photos or [])
        if any(p.get("file_unique_id") == photo.file_unique_id for p in photos):
            return draft
        photos.append(
            {"file_id": photo.file_id, "file_unique_id": photo.file_unique_id, "pos": photo.pos}
        )
        draft.photos = photos
        await self.session.flush()
        return draft

    async def discard_draft(self, draft: ShopProductDraft) -> None:
        draft.status = "discarded"
        await self.session.flush()

    async def list_open_drafts_for_shop(self, shop_id: int) -> Sequence[ShopProductDraft]:
        stmt = (
            select(ShopProductDraft)
            .where(ShopProductDraft.shop_id == shop_id, ShopProductDraft.status == "draft")
            .order_by(ShopProductDraft.id.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # ── photo blobs ───────────────────────────────────────────────────────

    async def store_photo_blob(
        self,
        *,
        file_unique_id: str,
        file_id: str,
        data: bytes,
        shop_id: int | None = None,
        mime_type: str = "image/jpeg",
        width: int | None = None,
        height: int | None = None,
    ) -> ProductPhotoBlob:
        """Persist the bytes, or refresh the handle if we already hold them.

        Re-uploading the same image keeps one row: `file_unique_id` is stable
        per image, while `file_id` can change, so the newer handle wins.
        """
        existing = await self.get_photo_blob(file_unique_id)
        if existing is not None:
            existing.file_id = file_id
            await self.session.flush()
            return existing

        blob = ProductPhotoBlob(
            file_unique_id=file_unique_id,
            file_id=file_id,
            shop_id=shop_id,
            mime_type=mime_type,
            byte_size=len(data),
            width=width,
            height=height,
            data=data,
        )
        self.session.add(blob)
        await self.session.flush()
        return blob

    async def get_photo_blob(self, file_unique_id: str) -> ProductPhotoBlob | None:
        stmt = select(ProductPhotoBlob).where(ProductPhotoBlob.file_unique_id == file_unique_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # ── moderation ────────────────────────────────────────────────────────

    async def list_pending_listings(self, limit: int = 50) -> Sequence[ShopProduct]:
        stmt = (
            select(ShopProduct)
            .where(ShopProduct.moderation_status == "pending")
            .order_by(ShopProduct.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def set_moderation_status(self, shop_product_id: int, status: str) -> ShopProduct | None:
        product = await self.session.get(ShopProduct, shop_product_id)
        if product is None:
            return None
        product.moderation_status = status
        await self.session.flush()
        return product

    async def count_pending_listings(self) -> int:
        stmt = select(ShopProduct.id).where(ShopProduct.moderation_status == "pending")
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    # ── applying a finished draft ─────────────────────────────────────────

    async def find_existing_offer(
        self,
        shop_id: int,
        canonical_id: int | None,
        pack_size: Decimal,
        pack_unit_code: str,
    ) -> ShopProduct | None:
        """Match the natural key of the offers table so re-listing updates in place."""
        stmt = select(ShopProduct).where(
            ShopProduct.shop_id == shop_id,
            ShopProduct.canonical_id == canonical_id,
            ShopProduct.pack_size == pack_size,
            ShopProduct.pack_unit_code == pack_unit_code,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
