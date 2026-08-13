from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories.ops_repo import OpsRepository
from app.db.session import get_db_session
from app.web.auth import require_admin
from app.web.templates_env import templates

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    ops_repo = OpsRepository(session)
    rows = await ops_repo.list_recent_daily_metrics(limit=30)
    return templates.TemplateResponse(request, "dashboard.html", {"rows": rows})


@router.get("/llm-cost", response_class=HTMLResponse)
async def llm_cost(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _admin: str = Depends(require_admin),
) -> HTMLResponse:
    ops_repo = OpsRepository(session)
    since = datetime.now(UTC) - timedelta(days=settings.admin_llm_cost_window_days)
    cost_by_purpose = await ops_repo.get_llm_cost_by_purpose(since)
    total_cost = sum(cost_by_purpose.values()) if cost_by_purpose else 0
    return templates.TemplateResponse(
        request,
        "llm_cost.html",
        {
            "cost_by_purpose": cost_by_purpose,
            "total_cost": total_cost,
            "window_days": settings.admin_llm_cost_window_days,
        },
    )
