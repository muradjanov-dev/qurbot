import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("REGISTER_WEBHOOK", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# The dispatcher is a module-level singleton, so its FSM storage is created
# once and reused by every test. A RedisStorage pool binds to whichever event
# loop touches it first, and pytest-asyncio gives each test a fresh loop, so
# the second test to feed an update through it died with "Event loop is
# closed". Tests have no Redis to talk to anyway.
os.environ.setdefault("FSM_USE_REDIS", "false")

import app.db.models  # noqa: F401
from app.db.base import Base


@pytest_asyncio.fixture
async def test_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
