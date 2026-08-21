"""Full catalogue view for operators.

Separate from /admin/offers, which lists what shops are selling. This lists
what the catalogue *contains* -- including products currently switched off for
customers by the launch allowlist, because an operator who cannot see what they
have hidden cannot judge whether hiding it was right.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin/products", tags=["admin-products"])

PAGE_SIZE = 50


@router.get("", response_class=HTMLResponse)
async def list_products(
    request: Request,
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    repo = CatalogRepository(session)
    offset = (page - 1) * PAGE_SIZE
    rows, total = await repo.admin_list_products(search=q, offset=offset, limit=PAGE_SIZE)

    enabled = set(settings.enabled_category_slugs)
    items = []
    for product, offer_count, min_price in rows:
        category = product.category
        slug = category.slug if category else None
        items.append(
            {
                "product": product,
                "offer_count": offer_count,
                "min_price": min_price,
                "category_name": category.name_uz if category else "—",
                # Shown so an operator can see at a glance which rows are live
                # for customers and which are only visible here.
                "customer_visible": (not enabled) or (slug in enabled),
            }
        )

    return templates.TemplateResponse(
        request,
        "products.html",
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            "q": q or "",
            "scope_active": bool(enabled),
        },
    )
