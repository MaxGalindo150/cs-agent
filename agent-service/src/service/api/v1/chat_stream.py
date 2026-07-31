"""Streaming chat endpoint (SSE) — tokens as they are generated.

``agent.respond(stream=True)`` runs the loop with an observer that emits token
deltas; here we bridge that to Server-Sent Events. The turn runs as a background
task pushing events into a queue; the SSE generator drains it and yields
``session`` (the id, first, so the client can continue the thread), ``delta``
(live text), the activity events below, then a terminal ``done`` (full reply)
or ``error``.

Activity events exist so the UI can show what the turn is *doing* while it is
still doing it, rather than a blank pause:

- ``gate``       — memory retrieval was decided (``{"decision"}``).
- ``tool_start`` — a tool is about to run (``{"tool", "label"}``). ``label`` is
  written by the tool itself (``agent.tools.registry.Tool.progress_label``), so
  the client renders progress without knowing which tools exist.
- ``tool``       — that tool finished (``{"tool", "args", "output"}``).

``tool_start``/``tool`` pair up by tool name in arrival order: the loop runs a
batch concurrently, so N starts are emitted, then N results as they land.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import anthropic
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent.app import Agent
from agent.identity import Principal
from service.api.v1.chat import ChatRequest, session_title
from service.core.agent import get_agent
from service.core.identity import get_principal

log = structlog.get_logger()

router = APIRouter(tags=["chat"])

_DONE = object()  # sentinel: the turn finished producing events


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    agent: Agent = Depends(get_agent),
    principal: Principal | None = Depends(get_principal),
) -> StreamingResponse:
    log.info(
        "chat_stream.principal_resolved",
        user_id=principal.user_id if principal else None,
    )

    # New conversation → mint a session up front (before any bytes are
    # streamed), titled with the message that opened it.
    session_id = req.session_id or await agent.start_session(
        session_title(req.message), principal=principal
    )
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def observer(kind: str, event: dict[str, Any]) -> None:
        # Runs inside the loop's streaming read; hand deltas to the SSE side.
        if kind == "text":
            queue.put_nowait(("delta", event["delta"]))
        elif kind == "gate":
            # Only the decision, never `reason` — that is the fast model's
            # free text about the user's message, which is not for display.
            queue.put_nowait(("gate", {"decision": event["decision"]}))
        elif kind == "tool_start":
            # `label` is what the UI renders; `tool` is only how the client
            # pairs this with the completion event below.
            queue.put_nowait(
                ("tool_start", {"tool": event["tool"], "label": event["label"]})
            )
        elif kind == "tool":
            # Surface the tool call for transparency: name + args + a short
            # preview of the result (the full result stays inside the loop).
            queue.put_nowait(
                (
                    "tool",
                    {
                        "tool": event["tool"],
                        "args": event["args"],
                        "output": event["output"][:500],
                    },
                )
            )
        elif kind == "limit_reached":
            queue.put_nowait(("limit_reached", event))

    async def drive() -> None:
        try:
            result = await agent.respond(
                session_id,
                req.message,
                observer=observer,
                source="api",
                stream=True,
                principal=principal,
            )
            queue.put_nowait(("done", result.reply))
        except anthropic.APIError as exc:
            # Mid-stream: headers are already sent, so surface the failure as an
            # SSE event (never a raw trace) instead of a 502.
            log.error("llm.provider_error", error=str(exc), path="/v1/chat/stream")
            queue.put_nowait(("error", "The assistant is temporarily unavailable."))
        except Exception as exc:
            # Any non-provider failure must not break the stream silently — emit
            # an opaque error event and log the detail server-side.
            log.error(
                "chat_stream.unexpected_error",
                error=str(exc),
                path="/v1/chat/stream",
            )
            queue.put_nowait(("error", "Something went wrong while streaming."))
        finally:
            queue.put_nowait(_DONE)

    async def events() -> AsyncIterator[str]:
        # First frame: the session id, so the client can continue this thread.
        yield _sse("session", {"session_id": str(session_id)})
        task = asyncio.create_task(drive())
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    break
                kind, payload = item
                yield _sse(kind, payload)
        finally:
            # Client disconnected (or generator closed): cancel the turn so it
            # stops calling the provider — burning tokens after the client is
            # gone is costly on Cloud Run.
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(events(), media_type="text/event-stream")
