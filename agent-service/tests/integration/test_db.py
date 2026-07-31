"""Behavioural tests for the Database wrapper itself (real PostgreSQL)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from agent.memory.db import Database
from agent.memory.repositories import FactRepository


async def test_ping_reports_a_reachable_database(database: Database) -> None:
    assert await database.ping() is True


async def test_session_pins_the_search_path_to_the_owned_schema(
    database: Database,
) -> None:
    """Unqualified names must resolve under `agent`, not `public`."""
    async with database.session() as session:
        assert await session.scalar(sa.text("SELECT current_schema()")) == "agent"


async def test_session_rolls_back_when_the_body_raises(database: Database) -> None:
    """A failing unit of work must leave nothing behind."""

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        async with database.session() as session:
            await FactRepository(session).add("alex", "no debe persistir")
            raise Boom()

    async with database.session() as session:
        remaining = await session.scalar(sa.text("SELECT count(*) FROM agent.facts"))
    assert remaining == 0
