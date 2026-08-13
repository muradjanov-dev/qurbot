from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin/unmatched", tags=["admin-unmatched"])


@router.get("", response_class=HTMLResponse)
async def list_unmatched(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    ops_repo = OpsRepository(session)
    catalog_repo = CatalogRepository(session)
    queries = await ops_repo.get_top_unmatched(limit=50)
    products = await catalog_repo.list_canonical_products(limit=500)
    return templates.TemplateResponse(
        request, "unmatched.html", {"queries": queries, "products": products}
    )


@router.post("/{query_id}/create-alias")
async def create_alias(
    query_id: int,
    canonical_id: int = Form(...),
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    ops_repo = OpsRepository(session)
    catalog_repo = CatalogRepository(session)
    query = await ops_repo.get(query_id)
    if query:
        alias = await catalog_repo.create_approved_alias(
            canonical_id=canonical_id,
            alias_norm=query.normalized,
            alias_raw=query.raw_text,
        )
        await ops_repo.mark_unmatched_resolved(query_id, alias.id)
    return RedirectResponse("/admin/unmatched", status_code=303)


@router.post("/{query_id}/mark-junk")
async def mark_junk(
    query_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> RedirectResponse:
    ops_repo = OpsRepository(session)
    await ops_repo.mark_unmatched_junk(query_id)
    return RedirectResponse("/admin/unmatched", status_code=303)
