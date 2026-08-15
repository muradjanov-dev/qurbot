"""Admin review of owner-supplied listing media.

Only the media and description are gated here. The price of a pending listing
is live and competing in quotes from the moment it is saved -- withholding a
shop's prices because nobody has looked at their photo yet would punish them
for uploading one.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.listing_repo import ListingRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin", tags=["admin-listings"])


@router.get("/listings", response_class=HTMLResponse)
async def list_pending(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> Response:
    repo = ListingRepository(session)
    listings = await repo.list_pending_listings(limit=100)
    return templates.TemplateResponse(request, "listings.html", {"listings": listings})


@router.post("/listings/{shop_product_id}/approve")
async def approve_listing(
    shop_product_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    repo = ListingRepository(session)
    await repo.set_moderation_status(shop_product_id, "approved")
    await session.commit()
    return RedirectResponse("/admin/listings", status_code=303)


@router.post("/listings/{shop_product_id}/reject")
async def reject_listing(
    shop_product_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    """Reject the media, keep the offer.

    Clearing the photos rather than deactivating the product is deliberate: a
    bad photo is not a reason to pull a real price out of the market.
    """
    repo = ListingRepository(session)
    product = await repo.set_moderation_status(shop_product_id, "rejected")
    if product is not None:
        product.photos = []
    await session.commit()
    return RedirectResponse("/admin/listings", status_code=303)


@router.get("/photo/{file_unique_id}")
async def serve_photo(
    file_unique_id: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> Response:
    """Serve an uploaded photo from our own copy.

    Reads the stored bytes rather than proxying Telegram: a file_id is scoped to
    the bot that received it and cannot be rendered in an <img> tag at all, so
    the durable blob is the only thing that reliably works here.
    """
    repo = ListingRepository(session)
    blob = await repo.get_photo_blob(file_unique_id)
    if blob is None:
        return Response(status_code=404)
    return StreamingResponse(
        io.BytesIO(blob.data),
        media_type=blob.mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
