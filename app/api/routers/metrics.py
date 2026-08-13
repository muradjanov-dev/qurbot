"""Prometheus scrape endpoint (SPEC §12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import db_pool_checked_out, db_pool_size, stale_price_offers
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import engine, get_db_session

router = APIRouter()


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_db_session)) -> Response:
    shop_repo = ShopRepository(session)
    stale_price_offers.set(await shop_repo.count_stale_offers())

    try:
        pool = engine.pool
        db_pool_size.set(pool.size())  # type: ignore[attr-defined]
        db_pool_checked_out.set(pool.checkedout())  # type: ignore[attr-defined]
    except (AttributeError, NotImplementedError):
        pass  # NullPool (e.g. sqlite in tests) doesn't track these.

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
