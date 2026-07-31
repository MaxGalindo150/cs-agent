"""Chat endpoint — one user message in, one reply out, over the agent loop.

Stateless per request: the caller passes a ``session_id`` to continue a
conversation, or omits it to start a new one (the id is returned so the client
can send it on later turns). The ``Agent`` loads that conversation's history from
Postgres, runs the turn, persists it, and traces it — nothing conversation-
specific lives in the process between requests (CLAUDE.md §9).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agent.app import Agent
from service.core.agent import get_agent

router = APIRouter(tags=["chat"])

# A session's title is its opening user message, capped to something a sidebar
# can show. Stamped once at creation, so the label never shifts under the user
# on later turns (and the conversation list needs no derived query).
_TITLE_CHARS = 120


def session_title(message: str) -> str:
    return message[:_TITLE_CHARS]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Conversation to continue. Omit to start a new one; the created id is "
            "returned so the client can send it on later turns."
        ),
    )


class ChatResponse(BaseModel):
    reply: str
    iterations: int
    session_id: uuid.UUID


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    agent: Agent = Depends(get_agent),
) -> ChatResponse:
    # New conversation → mint a session up front (chat_messages FKs to it),
    # titled with the message that opened it.
    session_id = req.session_id or await agent.start_session(session_title(req.message))
    result = await agent.respond(session_id, req.message, source="api")
    return ChatResponse(
        reply=result.reply,
        iterations=result.iterations,
        session_id=session_id,
    )
