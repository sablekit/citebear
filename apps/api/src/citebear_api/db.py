"""Async database engine and session management."""

import asyncio
import sys
from collections.abc import AsyncIterator, Coroutine
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from citebear_api.config import get_settings


def async_database_url(url: str) -> str:
    """Normalize a standard postgres URL to SQLAlchemy's async psycopg dialect."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        async_database_url(get_settings().database_url),
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with get_session_factory()() as session:
        yield session


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """asyncio.run for DB-touching entrypoints (CLIs, scripts).

    Windows dev machines default to the proactor loop, which async
    psycopg cannot use; this pins the selector loop there.
    """
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(coro)
