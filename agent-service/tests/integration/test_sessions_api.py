"""Integration tests for the conversation-browsing API (no LLM, real Postgres).

These endpoints are pure data access over the test database, so they are worth
testing against the real thing rather than a fake: the ordering comes from
Postgres (`last_activity_at desc`), and the delete relies on the
``chat_messages -> chat_sessions`` FK cascade, which only a real database
enforces.

``get_database`` is overridden with the migrated test pool; nothing else in the
app is touched, so the routes run exactly as they do in production.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa

from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from service.core.agent import get_database
from service.main import create_app


@pytest.fixture
async def api(database: Database) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_database] = lambda: database
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_lists_sessions_most_recently_active_first(
    api: httpx.AsyncClient, database: Database
) -> None:
    # Separate transactions: now() is the transaction timestamp in Postgres, so
    # activity ordering is only meaningful across separate units of work.
    async with database.session() as s:
        older_id = (await SessionRepository(s).create_session(title="viejo")).id
    async with database.session() as s:
        newer_id = (await SessionRepository(s).create_session(title="nuevo")).id
    async with database.session() as s:
        # Touch the older one so it climbs back to the top.
        await SessionRepository(s).append_message(older_id, "user", "sigo aquí")

    resp = await api.get("/v1/sessions")

    assert resp.status_code == 200
    body = resp.json()
    assert [row["id"] for row in body] == [str(older_id), str(newer_id)]
    assert [row["title"] for row in body] == ["viejo", "nuevo"]


async def test_lists_messages_in_insertion_order(
    api: httpx.AsyncClient, database: Database
) -> None:
    async with database.session() as s:
        repo = SessionRepository(s)
        session_id = (await repo.create_session(title="hilo")).id
        await repo.append_message(session_id, "user", "hola")
        await repo.append_message(session_id, "assistant", "qué tal")
        await repo.append_message(session_id, "user", "bien")

    resp = await api.get(f"/v1/sessions/{session_id}/messages")

    assert resp.status_code == 200
    body = resp.json()
    # Ordered by seq, not created_at — all three share a transaction timestamp.
    assert [(m["role"], m["content"]) for m in body] == [
        ("user", "hola"),
        ("assistant", "qué tal"),
        ("user", "bien"),
    ]


async def test_messages_of_unknown_session_is_404_not_empty(
    api: httpx.AsyncClient,
) -> None:
    """A client holding a deleted id must be able to tell it apart from a
    conversation that simply has no messages yet."""
    resp = await api.get(f"/v1/sessions/{uuid.uuid4()}/messages")

    assert resp.status_code == 404


async def test_malformed_session_id_is_rejected_at_the_boundary(
    api: httpx.AsyncClient,
) -> None:
    resp = await api.get("/v1/sessions/not-a-uuid/messages")

    assert resp.status_code == 422


async def test_delete_removes_the_session_and_cascades_to_messages(
    api: httpx.AsyncClient, database: Database
) -> None:
    async with database.session() as s:
        repo = SessionRepository(s)
        session_id = (await repo.create_session(title="a borrar")).id
        await repo.append_message(session_id, "user", "hola")
        await repo.append_message(session_id, "assistant", "adiós")

    resp = await api.delete(f"/v1/sessions/{session_id}")
    assert resp.status_code == 204

    async with database.session() as s:
        assert await SessionRepository(s).get_session(session_id) is None
        # The FK is ON DELETE CASCADE, so the log went with it — verified
        # against the real schema, which is the only place that constraint lives.
        orphans = await s.scalar(
            sa.text("SELECT count(*) FROM agent.chat_messages WHERE session_id = :sid"),
            {"sid": session_id},
        )
        assert orphans == 0


async def test_deleting_a_missing_session_is_404(api: httpx.AsyncClient) -> None:
    resp = await api.delete(f"/v1/sessions/{uuid.uuid4()}")

    assert resp.status_code == 404


async def test_limit_is_bounded(api: httpx.AsyncClient) -> None:
    """The page size is capped at the boundary so a caller cannot ask for the
    whole table."""
    assert (await api.get("/v1/sessions", params={"limit": 0})).status_code == 422
    assert (await api.get("/v1/sessions", params={"limit": 999})).status_code == 422
