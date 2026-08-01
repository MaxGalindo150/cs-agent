"""Integration tests for the escalate_to_human tool against a real PostgreSQL.

`needs_human` is a first-class result (CLAUDE.md §2): this tool is the only
way a session gets flagged, and the flag is a deterministic DB write, not a
promise the model makes on its own.
"""

from __future__ import annotations

import uuid

from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from agent.tools.context import ToolContext
from agent.tools.implementations.escalation import make_escalate_to_human_tool


async def _new_session(db: Database, user_id: str | None = None) -> uuid.UUID:
    async with db.session() as session:
        chat = await SessionRepository(session).create_session(user_id=user_id)
    return chat.id


def test_tool_needs_context_and_no_identity_requirement(database: Database) -> None:
    tool = make_escalate_to_human_tool(database)
    assert tool.needs_context is True
    assert tool.requires_identity is False


async def test_escalate_marks_the_session_and_reason(database: Database) -> None:
    session_id = await _new_session(database, user_id="usr_alice")
    ctx = ToolContext(principal=None, session_id=session_id)

    out = await make_escalate_to_human_tool(database).fn(
        ctx, reason="duplicate payment, refund needed"
    )

    assert "Flagged this conversation" in out
    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
        assert row is not None
        assert row.escalated_at is not None
        assert row.escalation_reason == "duplicate payment, refund needed"


async def test_escalate_works_for_an_anonymous_session(database: Database) -> None:
    """The whole point of needs_context over requires_identity: an anonymous
    visitor can still be escalated."""
    session_id = await _new_session(database)  # no user_id
    ctx = ToolContext(principal=None, session_id=session_id)

    out = await make_escalate_to_human_tool(database).fn(ctx, reason="can't log in")

    assert "Flagged this conversation" in out


async def test_escalate_is_idempotent(database: Database) -> None:
    """A second escalation call must not overwrite the first reason, and
    must tell the model it's already handled — not repeat the flag."""
    session_id = await _new_session(database, user_id="usr_alice")
    ctx = ToolContext(principal=None, session_id=session_id)
    tool = make_escalate_to_human_tool(database)
    await tool.fn(ctx, reason="first reason")

    out = await tool.fn(ctx, reason="second reason")

    assert out == "This conversation was already flagged for a human agent."
    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
        assert row is not None
        assert row.escalation_reason == "first reason"


async def test_escalate_without_a_reason_is_a_helpful_message(
    database: Database,
) -> None:
    session_id = await _new_session(database, user_id="usr_alice")
    ctx = ToolContext(principal=None, session_id=session_id)

    out = await make_escalate_to_human_tool(database).fn(ctx)

    assert "needs a reason" in out
    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
        assert row is not None
        assert row.escalated_at is None  # never wrote anything
