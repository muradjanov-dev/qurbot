"""Turning a shop owner's draft into a live, comparable offer.

Two things make this more than a straight INSERT. First, the listing has to be
resolved against the canonical catalog or it can never appear in a quote, since
the optimizer only ever queries by canonical_id. Second, the price has to be
reduced to a price-per-base-unit using the real unit factors (SPEC §5) -- a
50 kg bag at 52,000 is 1,040/kg, and storing 52,000 there would make the shop
look 50x more expensive than everyone else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import IncompatibleUnitsError
from app.db.models.shop import PriceHistory, ShopProduct, ShopProductDraft
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.listing_repo import ListingRepository, draft_to_domain
from app.db.repositories.ops_repo import OpsRepository
from app.domain.listing import (
    ListingCard,
    ListingDraft,
    PhotoRef,
    build_listing_card,
    draft_price_per_base_unit,
    validate_draft,
)
from app.domain.matching.models import MatchDecision
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.services.catalog_service import CatalogService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DraftMatch:
    canonical_id: int | None
    canonical_name: str | None
    base_unit: str
    confidence: float


@dataclass(frozen=True)
class ApplyOutcome:
    shop_product_id: int
    canonical_id: int | None
    display_name: str
    media_pending: bool


class ListingService:
    def __init__(
        self,
        session: AsyncSession,
        listing_repo: ListingRepository,
        catalog_repo: CatalogRepository,
        ops_repo: OpsRepository,
        catalog_service: CatalogService | None = None,
    ) -> None:
        self.session = session
        self.listing_repo = listing_repo
        self.catalog_repo = catalog_repo
        self.ops_repo = ops_repo
        self.catalog_service = catalog_service or CatalogService(catalog_repo, ops_repo)

    # ── matching ──────────────────────────────────────────────────────────

    async def match_draft(self, row: ShopProductDraft, *, log_unmatched: bool = True) -> DraftMatch:
        """Resolve the owner's product name against the catalog.

        A known category narrows the candidate pool before the search LIMIT is
        applied, which is the cheapest accuracy win available here.

        `log_unmatched` exists because this is called from read-only paths too
        (offering pack suggestions, rendering a preview). Recording an unmatched
        query from those would count the same product several times and skew the
        admin queue's ordering, which is sorted by how often a term is asked for.
        """
        if not row.name.strip():
            return DraftMatch(None, None, row.pack_unit_code or "dona", 0.0)

        category_ids: list[int] | None = None
        if row.category_id is not None:
            category_ids = await self.catalog_repo.get_category_subtree_ids(row.category_id)

        parsed = ParsedLine(
            line_no=1,
            raw_text=row.name,
            parsed_name=row.name,
            qty=Decimal("1"),
            unit_code=row.pack_unit_code,
            needs_review=False,
        )
        decision = await self._match_with_category(parsed, category_ids)

        if decision.canonical_id is None:
            if log_unmatched:
                # Unresolved listings are logged so the admin queue grows the
                # catalog rather than the product silently vanishing (§6 st.4).
                await self.ops_repo.record_unmatched_query(
                    raw_text=row.name,
                    normalized=normalize_query(row.name).text_norm,
                    user_id=None,
                )
            return DraftMatch(None, None, row.pack_unit_code or "dona", 0.0)

        canonical = await self.catalog_repo.get(decision.canonical_id)
        if canonical is None:
            return DraftMatch(None, None, row.pack_unit_code or "dona", 0.0)

        return DraftMatch(
            canonical_id=canonical.id,
            canonical_name=canonical.name_uz,
            base_unit=canonical.base_unit_code or row.pack_unit_code or "dona",
            confidence=decision.confidence,
        )

    async def _match_with_category(
        self, parsed: ParsedLine, category_ids: list[int] | None
    ) -> MatchDecision:
        _line, decision = await self.catalog_service.match_parsed_line(
            parsed, category_ids=category_ids
        )
        return decision

    # ── applying ──────────────────────────────────────────────────────────

    async def apply_draft(self, row: ShopProductDraft) -> ApplyOutcome:
        """Write the draft into shop_products. Raises if the draft is not valid.

        Re-listing the same product/pack updates the existing offer in place
        rather than creating a duplicate, matching the natural key already
        enforced by uq_shop_products_offer.
        """
        domain_draft = draft_to_domain(row)
        errors = validate_draft(
            domain_draft,
            max_photos=settings.listing_max_photos,
            max_name_len=settings.listing_max_name_len,
            max_description_len=settings.listing_max_description_len,
        )
        if errors:
            raise ValueError(f"draft {row.id} is not ready to apply: {[e.value for e in errors]}")

        match = await self.match_draft(row)
        price_per_base = self._price_per_base_unit(domain_draft, match.base_unit)

        pack_unit = row.pack_unit_code or "dona"
        pack_size = row.pack_size or Decimal("1")
        has_media = bool(row.photos) or bool(row.description)

        existing = await self.listing_repo.find_existing_offer(
            shop_id=row.shop_id,
            canonical_id=match.canonical_id,
            pack_size=pack_size,
            pack_unit_code=pack_unit,
        )

        if existing is not None:
            product = existing
        else:
            product = ShopProduct(
                shop_id=row.shop_id,
                canonical_id=match.canonical_id,
                raw_name=row.name,
                raw_unit=pack_unit,
                pack_size=pack_size,
                pack_unit_code=pack_unit,
                price_per_pack=row.price_per_pack or Decimal("0"),
                price_per_base_unit=price_per_base,
                currency="UZS",
                min_qty=Decimal("1"),
            )
            self.session.add(product)

        product.raw_name = row.name
        product.description = row.description
        product.photos = list(row.photos or [])
        product.stock_qty = row.stock_qty
        product.proposed_category_id = row.category_id
        product.price_per_pack = row.price_per_pack or Decimal("0")
        product.price_per_base_unit = price_per_base
        product.stock_status = self._stock_status_for(row.stock_qty)
        product.is_active = True
        product.staleness_state = "fresh"
        product.updated_by = "shop"
        product.updated_at = datetime.now(UTC)
        # Owner-supplied media is unreviewed; the price is not. Quoting is never
        # gated on this -- only whether customers see the photo/description.
        product.moderation_status = "pending" if has_media else "approved"

        await self.session.flush()

        self.session.add(
            PriceHistory(
                shop_product_id=product.id,
                price_per_pack=product.price_per_pack,
                price_per_base_unit=price_per_base,
            )
        )

        row.status = "applied"
        row.matched_canonical_id = match.canonical_id
        row.match_confidence = Decimal(str(round(match.confidence, 2)))
        row.applied_shop_product_id = product.id
        await self.session.flush()

        logger.info(
            "listing_applied draft=%s shop_product=%s canonical=%s media_pending=%s",
            row.id,
            product.id,
            match.canonical_id,
            has_media,
        )
        return ApplyOutcome(
            shop_product_id=product.id,
            canonical_id=match.canonical_id,
            # The owner's own wording, never the catalog's. The canonical match
            # is what makes the offer findable, but renaming their listing to
            # it makes them doubt they saved the right product.
            display_name=row.name,
            media_pending=has_media,
        )

    def _price_per_base_unit(self, draft: ListingDraft, base_unit: str) -> Decimal:
        """Reduce to a comparable per-base-unit price, falling back safely.

        When the matched product's base unit cannot express the pack unit (the
        owner picked a unit from a different dimension), the pack unit is used
        as its own base rather than storing a cross-dimension number that would
        corrupt every comparison the optimizer makes.
        """
        try:
            return draft_price_per_base_unit(draft, base_unit=base_unit)
        except IncompatibleUnitsError:
            logger.warning(
                "listing_unit_mismatch pack_unit=%s base_unit=%s -- pricing against pack unit",
                draft.pack_unit,
                base_unit,
            )
            return draft_price_per_base_unit(draft, base_unit=draft.pack_unit or "dona")

    @staticmethod
    def _stock_status_for(stock_qty: Decimal | None) -> str:
        if stock_qty is None:
            return "in_stock"
        if stock_qty <= 0:
            return "out"
        if stock_qty <= Decimal("5"):
            return "low"
        return "in_stock"

    # ── presentation ──────────────────────────────────────────────────────

    async def build_card(
        self, product: ShopProduct, *, viewer_is_owner: bool = False
    ) -> ListingCard:
        """Assemble the customer-facing card for a stored offer."""
        canonical = product.canonical_product
        title = canonical.name_uz if canonical else product.raw_name
        base_unit = (canonical.base_unit_code if canonical else None) or (
            product.pack_unit_code or "dona"
        )
        attributes = (
            canonical.attributes if canonical and isinstance(canonical.attributes, dict) else None
        )
        photos = tuple(
            PhotoRef(
                file_id=str(p.get("file_id", "")),
                file_unique_id=str(p.get("file_unique_id", "")),
                pos=int(p.get("pos", idx)),
            )
            for idx, p in enumerate(product.photos or [])
        )
        # Owners always see their own media so they can tell it was received;
        # customers only after review.
        show_photos = viewer_is_owner or product.moderation_status == "approved"
        # The customer buys from QurBot, not from a named vendor. Leaving the
        # shop name off the card entirely -- rather than relying on each caller
        # to remember not to render it -- means a future customer-facing surface
        # cannot leak it by accident.
        shop_name = product.shop.name if (viewer_is_owner and product.shop) else None

        return build_listing_card(
            title=title,
            price_per_pack=product.price_per_pack,
            price_per_base_unit=product.price_per_base_unit,
            pack_size=product.pack_size,
            pack_unit=product.pack_unit_code or product.raw_unit,
            base_unit=base_unit,
            stock_status=product.stock_status,
            stock_qty=product.stock_qty,
            brand=canonical.brand if canonical else None,
            description=product.description,
            shop_name=shop_name,
            photos=photos,
            max_photos=settings.listing_max_photos,
            attributes=attributes,
            show_photos=show_photos,
        )
