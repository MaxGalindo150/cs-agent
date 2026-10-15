"""Conversation browsing — list past chats, reopen one, delete one.

Every route is scoped to the caller (service/core/session_access.py): a
list shows only their own conversations — none for an anonymous visitor, whose
sessions have no owner to list by — and reading or deleting one requires
having started it.

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
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from agent.identity import Principal
from agent.memory.db import Database
from agent.memory.repositories import FeedbackRepository, SessionRepository
from service.core.agent import get_database
from service.core.identity import get_principal
from service.core.session_access import SessionAccess

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
    # Per-turn telemetry, including the ordered text/tool-call trail
    # (`meta["segments"]`) a client needs to render tool activity in place on
    # reload — absent on user messages and on turns logged before this existed.
    meta: dict[str, Any] | None
    created_at: datetime
    # The caller's own vote on this reply, if any — so a reloaded transcript
    # shows the thumb they picked.
    feedback: Literal["up", "down"] | None = None


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    db: Database = Depends(get_database),
    principal: Principal | None = Depends(get_principal),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SessionSummary]:
    """The caller's past conversations, most recently active first."""
    if principal is None:
        return []
    async with db.session() as session:
        rows = await SessionRepository(session).list_sessions(
            limit, user_id=principal.user_id
        )
        return [SessionSummary.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_session_messages(
    session_id: uuid.UUID,
    db: Database = Depends(get_database),
    principal: Principal | None = Depends(get_principal),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[MessageOut]:
    """The full transcript of one conversation, oldest first.

    404 when the session does not exist (or isn't the caller's), so a client
    holding a stale id can tell "deleted" apart from "empty" and drop it.
    """
    await SessionAccess(lambda: db).require(session_id, principal)
    async with db.session() as session:
        rows = await SessionRepository(session).list_messages(session_id, limit)
        ratings = await FeedbackRepository(session).ratings_for_session(session_id)
    messages = [MessageOut.model_validate(row) for row in rows]
    for message in messages:
        rating = ratings.get(message.id)
        if rating is not None:
            message.feedback = "up" if rating > 0 else "down"
    return messages


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    db: Database = Depends(get_database),
    principal: Principal | None = Depends(get_principal),
) -> Response:
    """Delete a conversation and its messages (FK cascade). 404 if already gone."""
    await SessionAccess(lambda: db).require(session_id, principal)
    async with db.session() as session:
        deleted = await SessionRepository(session).delete_session(session_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)


@router.put(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def rate_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: FeedbackIn,
    db: Database = Depends(get_database),
    principal: Principal | None = Depends(get_principal),
) -> Response:
    """Thumbs up/down on one of the caller's assistant replies; rating again
    replaces the vote. 404 when the session isn't the caller's or the
    message isn't a reply in it."""
    await SessionAccess(lambda: db).require(session_id, principal)
    async with db.session() as session:
        rated = await FeedbackRepository(session).rate(
            session_id,
            message_id,
            user_id=principal.user_id if principal else None,
            rating=1 if body.rating == "up" else -1,
            comment=(body.comment or "").strip() or None,
        )
    if not rated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_message_rating(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    db: Database = Depends(get_database),
    principal: Principal | None = Depends(get_principal),
) -> Response:
    """Withdraw the caller's vote on a reply. 204 even if there was none."""
    await SessionAccess(lambda: db).require(session_id, principal)
    async with db.session() as session:
        await FeedbackRepository(session).clear(session_id, message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
