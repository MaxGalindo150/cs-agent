"""Fixtures for tests that hit a real PostgreSQL (Level 1 — deterministic, no LLM).

These run against the compose Postgres locally and a service container in CI.
They use a dedicated **test database** (never the dev one), created on demand,
and apply the real Alembic migrations — so the migrations themselves are
exercised on every run, not just the models.

Point them elsewhere with ``AGENT_TEST_DATABASE_URL``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agent.memory.db import Database, DatabaseConfig
from alembic import command

_SERVICE_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_TEST_URL = "postgresql+asyncpg://csa:csa@localhost:5433/customer_support_test"

# Truncated between tests. CASCADE covers the chat_messages -> chat_sessions FK.
_TABLES = ("chat_messages", "chat_sessions", "facts", "episodes")


def _test_database_url() -> str:
    return os.environ.get("AGENT_TEST_DATABASE_URL", _DEFAULT_TEST_URL)


async def _create_database_if_missing(url: str) -> None:
    """Ensure the test database exists.

    CREATE DATABASE cannot run inside a transaction, nor from within the
    database being created — hence AUTOCOMMIT against the `postgres`
    maintenance database.
    """
    parts = urlsplit(url)
    database = parts.path.lstrip("/")
    admin_url = urlunsplit(parts._replace(path="/postgres"))

    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database},
            )
            if not exists:
                # Identifier, not a value — cannot be bound as a parameter. The
                # name comes from our own config, never from user input.
                await conn.execute(sa.text(f'CREATE DATABASE "{database}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    """Create the test database (if needed) and bring it to head.

    Sync + session-scoped on purpose: Alembic's env.py calls ``asyncio.run``,
    which cannot run inside an already-running event loop.
    """
    url = _test_database_url()
    asyncio.run(_create_database_if_missing(url))

    config = Config(str(_SERVICE_ROOT / "alembic.ini"))
    # env.py reads the URL from the environment; point it at the test DB.
    previous = os.environ.get("AGENT_DATABASE_URL")
    os.environ["AGENT_DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            del os.environ["AGENT_DATABASE_URL"]
        else:
            os.environ["AGENT_DATABASE_URL"] = previous
    return url


@pytest.fixture
async def database(migrated_database_url: str) -> AsyncIterator[Database]:
    """A Database bound to the migrated test DB, wiped after each test."""
    db = Database(DatabaseConfig(url=migrated_database_url))
    try:
        yield db
    finally:
        async with db.engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "TRUNCATE "
                    + ", ".join(f"agent.{table}" for table in _TABLES)
                    + " RESTART IDENTITY CASCADE"
                )
            )
        await db.dispose()


@pytest.fixture
async def db_session(database: Database) -> AsyncIterator[AsyncSession]:
    """A short-lived unit of work, the way production code takes one."""
    async with database.session() as session:
        yield session
