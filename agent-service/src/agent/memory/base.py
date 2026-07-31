"""Declarative base for the agent's PostgreSQL models.

All tables live under the owned ``agent`` schema (ADR-0002) — the isolation
boundary from sibling services in the shared database. The constraint naming
convention makes Alembic autogenerate deterministic and migrations reversible
(constraints get stable, predictable names instead of DB-assigned ones).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# The schema this service owns. Matches DatabaseConfig.schema (agent/memory/db.py)
# and version_table_schema in alembic/env.py.
SCHEMA = "agent"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
