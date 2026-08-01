"""Chat endpoint — one user message in, one reply out, over the agent loop.

Stateless per request: the caller passes a ``session_id`` to continue a
conversation, or omits it to start a new one (the id is returned so the client
can send it on later turns). The ``Agent`` loads that conversation's history from
Postgres, runs the turn, persists it, and traces it — nothing conversation-
specific lives in the process between requests (CLAUDE.md §9).
"""

from __future__ import annotations

import base64
import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from agent.app import Agent
from agent.identity import Principal
from agent.vision import Image
from service.core.agent import get_agent
from service.core.identity import get_principal

log = structlog.get_logger()

router = APIRouter(tags=["chat"])

# A session's title is its opening user message, capped to something a sidebar
# can show. Stamped once at creation, so the label never shifts under the user
# on later turns (and the conversation list needs no derived query).
_TITLE_CHARS = 120

# Anthropic's own per-image guidance; validated here so an oversized or
# malformed image 422s at the edge, never surfaces as an opaque provider
# error mid-turn (CLAUDE.md §6 — pydantic validation at every boundary).
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_IMAGES_PER_TURN = 4
# Base64 inflates by 4/3 (rounded up to the next multiple of 4): the longest
# `data` string that can possibly decode to _MAX_IMAGE_BYTES or fewer bytes.
# Checked as a cheap Field(max_length=...) BEFORE base64.b64decode ever runs —
# without it, an attacker-supplied multi-GB `data` string gets fully decoded
# (real memory/CPU spent) before the byte-count check below ever rejects it.
_MAX_IMAGE_BASE64_CHARS = 4 * ((_MAX_IMAGE_BYTES + 2) // 3)


def session_title(message: str) -> str:
    return message[:_TITLE_CHARS]


def _matches_media_type(decoded: bytes, media_type: str) -> bool:
    """A cheap magic-number sniff — not a full image decode, just enough to
    catch a mislabeled or non-image payload before it reaches the provider
    (e.g. ``aGVsbG8=`` decoding to the plain bytes ``hello``, declared as
    ``image/png``, must 422 here rather than surface as an opaque failure
    partway through a turn)."""
    if media_type == "image/png":
        return decoded.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return decoded.startswith(b"\xff\xd8\xff")
    if media_type == "image/gif":
        return decoded.startswith((b"GIF87a", b"GIF89a"))
    if media_type == "image/webp":
        return decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP"
    return False  # unreachable: media_type is already a validated Literal


class ImageInput(BaseModel):
    """One attached image: base64 data, no ``data:`` URI prefix. Context for
    the turn it arrives in — see ``agent/vision.py`` for why nothing about an
    image is ever persisted."""

    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"]
    data: str = Field(min_length=1, max_length=_MAX_IMAGE_BASE64_CHARS)

    @field_validator("data")
    @classmethod
    def _validate_base64_and_size(cls, v: str, info: ValidationInfo) -> str:
        try:
            decoded = base64.b64decode(v, validate=True)
        except ValueError as exc:
            raise ValueError("data must be valid base64") from exc
        if len(decoded) > _MAX_IMAGE_BYTES:
            limit_mb = _MAX_IMAGE_BYTES // (1024 * 1024)
            raise ValueError(f"image exceeds the {limit_mb}MB limit")
        # media_type is declared before data, so it's already validated and
        # present here — unless it itself failed validation, in which case
        # that failure is reported on its own and this check is skipped.
        media_type = info.data.get("media_type")
        if media_type is not None and not _matches_media_type(decoded, media_type):
            raise ValueError(f"data does not look like a valid {media_type} image")
        return v

    def to_agent_image(self) -> Image:
        return Image(media_type=self.media_type, data=self.data)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Conversation to continue. Omit to start a new one; the created id is "
            "returned so the client can send it on later turns."
        ),
    )
    images: list[ImageInput] = Field(
        default_factory=list,
        max_length=_MAX_IMAGES_PER_TURN,
        description="Images attached as context for this turn (see ImageInput).",
    )


class ChatResponse(BaseModel):
    reply: str
    iterations: int
    session_id: uuid.UUID


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    agent: Agent = Depends(get_agent),
    principal: Principal | None = Depends(get_principal),
) -> ChatResponse:
    log.info(
        "chat.principal_resolved",
        user_id=principal.user_id if principal else None,
    )

    # New conversation → mint a session up front (chat_messages FKs to it),
    # titled with the message that opened it.
    session_id = req.session_id or await agent.start_session(
        session_title(req.message), principal=principal
    )
    images = [img.to_agent_image() for img in req.images] or None
    result = await agent.respond(
        session_id, req.message, source="api", principal=principal, images=images
    )
    return ChatResponse(
        reply=result.reply,
        iterations=result.iterations,
        session_id=session_id,
    )
