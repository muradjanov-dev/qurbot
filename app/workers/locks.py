"""Postgres advisory locks so scheduled jobs are safe to overlap/re-run (SPEC §10)."""

from __future__ import annotations

import zlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


def _lock_key(job_name: str) -> int:
    return zlib.crc32(job_name.encode("utf-8"))


async def try_acquire_job_lock(session: AsyncSession, job_name: str) -> bool:
    """Transaction-scoped advisory lock: auto-released on commit/rollback.

    SQLite (used by the test suite) has no advisory locks, so it always succeeds there.
    """
    if settings.database_url.startswith("sqlite"):
        return True
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _lock_key(job_name)}
    )
    return bool(result.scalar())
