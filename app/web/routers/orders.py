from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.order_repo import OrderRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


@router.get("", response_class=HTMLResponse)
async def list_orders(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    order_repo = OrderRepository(session)
    orders = await order_repo.list_recent_orders(limit=100)
    return templates.TemplateResponse(request, "orders.html", {"orders": orders})
