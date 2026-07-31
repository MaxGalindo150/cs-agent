import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing `models` registers every mapped table on its metadata, which is what
# autogenerate diffs the live DB against (we read it back as models.Base.metadata
# below). SCHEMA is the owned `agent` schema (single source of truth in
# agent.memory.base): both the object DDL and Alembic's own version table live
# there, isolating this service's migration history from siblings in the shared
# database.
from agent.memory import models
from agent.memory.base import SCHEMA
from alembic import context

# Local-dev fallback; MUST match service/core/config.py's AGENT_DATABASE_URL
# default. Deployed environments set a real AGENT_DATABASE_URL (Secret Manager).
_LOCAL_DEFAULT_URL = (
    "postgresql+asyncpg://csa:csa@localhost:5433/customer_support"
)

# the Alembic Config object provides access to the .ini values.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# agent-service owns its .env locally; real env vars take precedence. We read
# AGENT_DATABASE_URL from the environment (not the .ini) so migrations use the
# same source of truth as the running service — and so no credentials live in a
# committed file. Migrations deliberately do NOT import service.core.config:
# that would pull in unrelated required settings (e.g. ANTHROPIC_API_KEY) just
# to run a migration.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("AGENT_DATABASE_URL", _LOCAL_DEFAULT_URL),
)

target_metadata = models.Base.metadata


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    """Restrict autogenerate to the schema this service owns. The database is
    shared; without this, autogenerate would compare `public` (and any sibling
    service's objects) against our empty metadata and propose to DROP them."""
    if type_ == "schema":
        return name == SCHEMA
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DBAPI needed)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=include_name,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # The owned schema must exist before Alembic creates its version table in
    # it. Idempotent; committed on its own so it is durable regardless of what
    # the migration transaction below does.
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    connection.commit()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async Engine and run migrations through a sync-bridged conn."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
