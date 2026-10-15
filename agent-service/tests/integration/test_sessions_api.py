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

# Tests run with ENVIRONMENT=dev (tests/conftest.py), where the trusted
# X-User-Id header stands in for a verified identity.
_AS_A = {"X-User-Id": "usr_a"}
_AS_B = {"X-User-Id": "usr_b"}


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
        older_id = (
            await SessionRepository(s).create_session(title="viejo", user_id="usr_a")
        ).id
    async with database.session() as s:
        newer_id = (
            await SessionRepository(s).create_session(title="nuevo", user_id="usr_a")
        ).id
    async with database.session() as s:
        # Touch the older one so it climbs back to the top.
        await SessionRepository(s).append_message(older_id, "user", "sigo aquí")

    resp = await api.get("/v1/sessions", headers=_AS_A)

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


# --- Scoped to the caller (docs/SECURITY.md §2) ------------------------------


async def test_list_shows_only_the_callers_sessions(
    api: httpx.AsyncClient, database: Database
) -> None:
    async with database.session() as s:
        repo = SessionRepository(s)
        mine = (await repo.create_session(title="mía", user_id="usr_a")).id
        await repo.create_session(title="ajena", user_id="usr_b")
        await repo.create_session(title="anónima")

    body = (await api.get("/v1/sessions", headers=_AS_A)).json()

    assert [row["id"] for row in body] == [str(mine)]


async def test_anonymous_list_is_empty_even_with_anonymous_sessions(
    api: httpx.AsyncClient, database: Database
) -> None:
    """Anonymous sessions have no owner to list by — listing them would show
    every visitor everyone else's conversations."""
    async with database.session() as s:
        await SessionRepository(s).create_session(title="anónima")

    resp = await api.get("/v1/sessions")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_messages_of_someone_elses_session_look_missing(
    api: httpx.AsyncClient, database: Database
) -> None:
    async with database.session() as s:
        repo = SessionRepository(s)
        theirs = (await repo.create_session(title="ajena", user_id="usr_b")).id
        await repo.append_message(theirs, "user", "privado")

    assert (
        await api.get(f"/v1/sessions/{theirs}/messages", headers=_AS_A)
    ).status_code == 404
    assert (await api.get(f"/v1/sessions/{theirs}/messages")).status_code == 404
    assert (
        await api.get(f"/v1/sessions/{theirs}/messages", headers=_AS_B)
    ).status_code == 200


async def test_cannot_delete_someone_elses_session(
    api: httpx.AsyncClient, database: Database
) -> None:
    async with database.session() as s:
        theirs = (
            await SessionRepository(s).create_session(title="ajena", user_id="usr_b")
        ).id

    resp = await api.delete(f"/v1/sessions/{theirs}", headers=_AS_A)

    assert resp.status_code == 404
    async with database.session() as s:
        assert await SessionRepository(s).get_session(theirs) is not None


# ---- feedback on replies ----------------------------------------------------


async def _thread(
    database: Database, user_id: str | None
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A session with one user message and one reply: (session, user msg, reply)."""
    async with database.session() as s:
        repo = SessionRepository(s)
        session_id = (await repo.create_session(title="hilo", user_id=user_id)).id
        question = await repo.append_message(session_id, "user", "¿mis órdenes?")
        reply = await repo.append_message(session_id, "assistant", "aquí están")
    return session_id, question.id, reply.id


async def test_a_reply_can_be_rated_rerated_and_cleared(
    api: httpx.AsyncClient, database: Database
) -> None:
    session_id, _, reply_id = await _thread(database, "usr_a")
    url = f"/v1/sessions/{session_id}/messages/{reply_id}/feedback"

    first = await api.put(
        url, json={"rating": "down", "comment": "no era eso"}, headers=_AS_A
    )
    again = await api.put(url, json={"rating": "up"}, headers=_AS_A)
    listed = await api.get(f"/v1/sessions/{session_id}/messages", headers=_AS_A)

    assert (first.status_code, again.status_code) == (204, 204)
    assert [m["feedback"] for m in listed.json()] == [None, "up"]
    async with database.session() as s:
        row = (
            await s.execute(
                sa.text(
                    "select rating, comment, user_id from agent.message_feedback "
                    "where message_id = :id"
                ),
                {"id": reply_id},
            )
        ).one()
    # Re-rating replaced the vote, comment included.
    assert tuple(row) == (1, None, "usr_a")

    cleared = await api.delete(url, headers=_AS_A)
    relisted = await api.get(f"/v1/sessions/{session_id}/messages", headers=_AS_A)

    assert cleared.status_code == 204
    assert [m["feedback"] for m in relisted.json()] == [None, None]


async def test_only_the_session_owner_can_rate(
    api: httpx.AsyncClient, database: Database
) -> None:
    session_id, _, reply_id = await _thread(database, "usr_a")

    resp = await api.put(
        f"/v1/sessions/{session_id}/messages/{reply_id}/feedback",
        json={"rating": "up"},
        headers=_AS_B,
    )

    assert resp.status_code == 404


async def test_only_replies_of_that_session_can_be_rated(
    api: httpx.AsyncClient, database: Database
) -> None:
    session_id, question_id, _ = await _thread(database, "usr_a")
    _, _, other_reply_id = await _thread(database, "usr_a")

    own_question = await api.put(
        f"/v1/sessions/{session_id}/messages/{question_id}/feedback",
        json={"rating": "up"},
        headers=_AS_A,
    )
    elsewhere = await api.put(
        f"/v1/sessions/{session_id}/messages/{other_reply_id}/feedback",
        json={"rating": "up"},
        headers=_AS_A,
    )
    bad_rating = await api.put(
        f"/v1/sessions/{session_id}/messages/{question_id}/feedback",
        json={"rating": "meh"},
        headers=_AS_A,
    )

    assert (own_question.status_code, elsewhere.status_code) == (404, 404)
    assert bad_rating.status_code == 422


async def test_deleting_the_session_takes_its_feedback(
    api: httpx.AsyncClient, database: Database
) -> None:
    session_id, _, reply_id = await _thread(database, "usr_a")
    await api.put(
        f"/v1/sessions/{session_id}/messages/{reply_id}/feedback",
        json={"rating": "up"},
        headers=_AS_A,
    )

    await api.delete(f"/v1/sessions/{session_id}", headers=_AS_A)

    async with database.session() as s:
        left = await s.scalar(sa.text("select count(*) from agent.message_feedback"))
    assert left == 0
