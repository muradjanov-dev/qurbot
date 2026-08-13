from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.shop_repo import ShopRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin/shops", tags=["admin-shops"])


@router.get("", response_class=HTMLResponse)
async def list_shops(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    shop_repo = ShopRepository(session)
    shops = await shop_repo.list_all(limit=200)
    return templates.TemplateResponse(request, "shops.html", {"shops": shops})


@router.post("/{shop_id}/verify")
async def verify_shop(
    shop_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    shop_repo = ShopRepository(session)
    await shop_repo.verify_shop(shop_id)
    return RedirectResponse("/admin/shops", status_code=303)


@router.post("/{shop_id}/deactivate")
async def deactivate_shop(
    shop_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    shop_repo = ShopRepository(session)
    await shop_repo.set_shop_active(shop_id, False)
    return RedirectResponse("/admin/shops", status_code=303)


@router.post("/{shop_id}/activate")
async def activate_shop(
    shop_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    shop_repo = ShopRepository(session)
    await shop_repo.set_shop_active(shop_id, True)
    return RedirectResponse("/admin/shops", status_code=303)
