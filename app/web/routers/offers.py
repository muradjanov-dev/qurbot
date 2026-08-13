from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.shop_repo import ShopRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin/offers", tags=["admin-offers"])


@router.get("", response_class=HTMLResponse)
async def list_offers(
    request: Request,
    state: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    shop_repo = ShopRepository(session)
    offers = await shop_repo.list_offers_by_staleness(staleness_state=state, limit=200)
    return templates.TemplateResponse(request, "offers.html", {"offers": offers})


@router.post("/bulk-deactivate")
async def bulk_deactivate(
    offer_ids: list[int] = Form(default=[]),
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    shop_repo = ShopRepository(session)
    await shop_repo.bulk_deactivate_offers(offer_ids)
    return RedirectResponse("/admin/offers", status_code=303)
