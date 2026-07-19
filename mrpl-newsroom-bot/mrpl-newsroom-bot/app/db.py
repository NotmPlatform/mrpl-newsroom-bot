from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None
_poller_lock: AsyncConnection | None = None


def configure_database(settings: Settings) -> None:
    global engine, session_factory
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=900,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_database() -> None:
    if engine is None:
        raise RuntimeError("Database is not configured")
    from app import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def acquire_poller_lock() -> bool:
    """Hold a PostgreSQL advisory lock for the whole polling process."""
    global _poller_lock
    if engine is None:
        raise RuntimeError("Database is not configured")
    _poller_lock = await engine.connect()
    result = await _poller_lock.execute(
        text("SELECT pg_try_advisory_lock(:key)"),
        {"key": 730524811},
    )
    return bool(result.scalar())


async def release_poller_lock() -> None:
    global _poller_lock
    if _poller_lock is not None:
        await _poller_lock.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": 730524811},
        )
        await _poller_lock.close()
        _poller_lock = None


async def close_database() -> None:
    await release_poller_lock()
    if engine is not None:
        await engine.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    if session_factory is None:
        raise RuntimeError("Database is not configured")
    async with session_factory() as session:
        yield session

