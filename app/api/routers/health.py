import asyncio

from fastapi import APIRouter, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_factory

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def check_database() -> bool:
    try:
        async with asyncio.timeout(settings.readiness_timeout_seconds):
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, TimeoutError):
        logger.warning("readiness_database_failed", exc_info=True)
        return False


async def check_redis() -> bool:
    client = Redis.from_url(settings.redis_url)
    try:
        async with asyncio.timeout(settings.readiness_timeout_seconds):
            await client.ping()
        return True
    except (RedisError, TimeoutError):
        logger.warning("readiness_redis_failed", exc_info=True)
        return False
    finally:
        await client.aclose()


@router.get("/ready")
async def readiness(response: Response) -> dict[str, object]:
    database_ok, redis_ok = await asyncio.gather(check_database(), check_redis())
    ready = database_ok and redis_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready else "unavailable",
        "checks": {"database": database_ok, "redis": redis_ok},
    }
