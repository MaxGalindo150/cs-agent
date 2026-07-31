"""Conversation browsing — list past chats, reopen one, delete one.

These are **transport concerns, not agent concerns**: the loop never lists or
deletes conversations, it only reads the history of the one it is answering
(``Memory.session_history``). So the queries live here and go straight to
``SessionRepository`` over the process-wide pool, instead of widening the
``Memory`` facade with methods the brain would never call (CLAUDE.md §4 — the
dependency arrow points service → agent, and this is the service side of it).

Each handler opens one short session and closes it before returning: no
connection is held across anything slow (CLAUDE.md §3). All three are cheap
indexed reads/one DELETE — there is no LLM call on this path at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from service.core.agent import get_database

router = APIRouter(tags=["sessions"])


class SessionSummary(BaseModel):
    """One row in the conversation list.

    ``title`` is the opening user message, stamped at creation (see
    service/api/v1/chat.py) — NULL only for sessions created before that, or
    by a caller that passed none.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    last_activity_at: datetime


class MessageOut(BaseModel):
    """One message of a transcript, as it was logged."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    db: Database = Depends(get_database),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SessionSummary]:
    """Past conversations, most recently active first."""
    async with db.session() as session:
        rows = await SessionRepository(session).list_sessions(limit)
        return [SessionSummary.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_session_messages(
    session_id: uuid.UUID,
    db: Database = Depends(get_database),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[MessageOut]:
    """The full transcript of one conversation, oldest first.

    404 when the session does not exist, so a client holding a stale id can
    tell "deleted" apart from "empty" and drop it.
    """
    async with db.session() as session:
        repo = SessionRepository(session)
        if await repo.get_session(session_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
        rows = await repo.list_messages(session_id, limit)
        return [MessageOut.model_validate(row) for row in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    db: Database = Depends(get_database),
) -> Response:
    """Delete a conversation and its messages (FK cascade). 404 if already gone."""
    async with db.session() as session:
        deleted = await SessionRepository(session).delete_session(session_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
