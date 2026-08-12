from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def get_engine(url: str | None = None, echo: bool | None = None) -> AsyncEngine:
    db_url = url or settings.database_url
    is_echo = settings.database_echo if echo is None else echo

    # Handle SQLite for in-memory testing vs PostgreSQL in dev/prod
    kwargs: dict[str, object] = {"echo": is_echo}
    if not db_url.startswith("sqlite"):
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow

    return create_async_engine(db_url, **kwargs)


engine = get_engine()
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
