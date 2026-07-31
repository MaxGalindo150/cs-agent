"""Apply pending Alembic migrations at startup (local/dev convenience).

Alembic's ``env.py`` drives its own event loop (``asyncio.run``), which cannot
run inside the already-running lifespan loop — so we run the upgrade in a worker
thread, where a fresh loop is fine (the same constraint the integration
conftest documents).

**Serverless caveat.** On Cloud Run this would run on every cold start, and each
scaling instance would attempt it — Alembic's advisory lock serializes them so it
is *safe*, but it adds startup latency and requires the runtime identity to hold
DDL privileges (a wider blast radius than a DML-only app). Prefer migrations as a
deploy step in prod and set ``RUN_MIGRATIONS_ON_STARTUP=false`` there; keep it on
for local dev (CLAUDE.md §3/§9).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.config import Config

from alembic import command

# migrations.py → core → service → src → agent-service (where alembic.ini lives).
_SERVICE_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    return Config(str(_SERVICE_ROOT / "alembic.ini"))


async def upgrade_to_head() -> None:
    """Bring the database to the latest migration.

    Runs Alembic (and its own ``asyncio.run``) in a worker thread so it never
    nests inside the caller's running event loop.
    """
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
