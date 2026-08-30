import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _build_database_url() -> URL:
    return URL.create(
        drivername="postgresql+asyncpg",
        username=os.environ.get("POSTGRES_USER", "POPULATE .env file"),
        password=os.environ.get("POSTGRES_PASSWORD", "POPULATE .env file"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "POPULATE .env file"),
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def start_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        raise RuntimeError("DB engine is already started")

    _engine = create_async_engine(_build_database_url())
    # expire_on_commit=False: avoids an implicit refresh query (which would need
    # an active event loop context) on attribute access after commit.
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def stop_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("DB engine is not started")
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
