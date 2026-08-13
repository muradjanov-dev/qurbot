from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.catalog_repo import CatalogRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin/aliases", tags=["admin-aliases"])


@router.get("", response_class=HTMLResponse)
async def list_aliases(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    catalog_repo = CatalogRepository(session)
    aliases = await catalog_repo.list_unapproved_aliases(limit=100)
    return templates.TemplateResponse(request, "aliases.html", {"aliases": aliases})


@router.post("/{alias_id}/approve")
async def approve_alias(
    alias_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    catalog_repo = CatalogRepository(session)
    await catalog_repo.approve_alias(alias_id)
    return RedirectResponse("/admin/aliases", status_code=303)


@router.post("/{alias_id}/reject")
async def reject_alias(
    alias_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    catalog_repo = CatalogRepository(session)
    await catalog_repo.reject_alias(alias_id)
    return RedirectResponse("/admin/aliases", status_code=303)
