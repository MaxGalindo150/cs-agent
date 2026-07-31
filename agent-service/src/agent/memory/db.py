"""Async PostgreSQL engine + session factory for the agent's durable memory.

Transport-neutral by construction: this module never imports `service`. The
transport builds a `DatabaseConfig` from its own settings (`AGENT_DATABASE_URL`)
and injects it at wiring time — the brain depends on this small abstraction, not
on the service (CLAUDE.md §4, ADR-0002).

Connection discipline (CLAUDE.md §3): a DB connection is NEVER held across an
LLM call. Sessions are short and scoped to a single unit of work — take one,
read/write, hand it back to the pool. No transaction spans a provider call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Connection settings for the agent's Postgres store.

    `url` must use an async driver (e.g. ``postgresql+asyncpg://…``). `schema`
    is the Postgres schema this service owns inside the shared database — the
    isolation boundary from sibling services (ADR-0002). Pool defaults are
    conservative for Cloud Run, where many small instances each hold a few
    connections; tune via env only once measured.
    """

    url: str
    schema: str = "agent"
    pool_size: int = 5
    max_overflow: int = 5
    pool_timeout: float = 10.0
    pool_recycle_seconds: int = 1800
    echo: bool = False


class Database:
    """Owns the async engine + session factory. One instance per process:
    build it at startup, `dispose()` it at shutdown.

    The connection ``search_path`` is pinned to ``<schema>,public`` so
    unqualified names resolve under the owned schema first, with `public`
    available for shared extensions.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: AsyncEngine = create_async_engine(
            config.url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle_seconds,
            pool_pre_ping=True,
            echo=config.echo,
            connect_args={
                "server_settings": {"search_path": f"{config.schema},public"}
            },
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A short-lived unit of work: commit on success, roll back on error.

        Keep the body small — never ``await`` an LLM (or other slow external)
        call while this session is open (CLAUDE.md §3).
        """
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """Cheap liveness check (``SELECT 1``) for readiness probes."""
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def dispose(self) -> None:
        """Close the pool. Call once, at process shutdown."""
        await self._engine.dispose()
