"""Contract tests for POST /v1/chat/stream (SSE, Level 1 — no network, no DB).

``get_agent`` is overridden with a fake Agent that drives the observer directly,
so these assert the SSE *bridge* — the ``session`` frame, ``delta`` / ``tool``
events, the terminal ``done``, and error handling — without a DB or LLM. The
loop's own streaming (deltas, fallback) is covered by ``tests/unit/test_loop.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from agent.loop.agent import LoopResult
from agent.observability import Observer
from service.core.agent import get_agent
from service.main import create_app

_SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class _StreamAgent:
    async def start_session(self, title: str | None = None) -> uuid.UUID:
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
    ) -> LoopResult:
        assert observer is not None
        observer("text", {"delta": "Hola"})
        observer("text", {"delta": " mundo"})
        return LoopResult(reply="Hola mundo", iterations=1)


@pytest.fixture
async def stream_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent] = _StreamAgent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_chat_stream_emits_session_then_deltas_then_done(
    stream_client: httpx.AsyncClient,
) -> None:
    body = ""
    async with stream_client.stream(
        "POST", "/v1/chat/stream", json={"message": "hola"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for chunk in resp.aiter_text():
            body += chunk

    # the session id comes first, so the client can continue the thread
    assert "event: session" in body
    assert str(_SESSION_ID) in body
    # tokens arrived live as SSE delta events...
    assert "event: delta" in body
    assert "Hola" in body
    assert "mundo" in body
    # ...followed by a terminal done event carrying the full reply
    assert "event: done" in body
    assert "Hola mundo" in body


async def test_chat_stream_accepts_identity_headers(
    stream_client: httpx.AsyncClient,
) -> None:
    # Dev-only stub (service/core/identity.py) — the route must accept the
    # headers without erroring, whether or not a fake Agent does anything
    # with the resolved Principal yet.
    async with stream_client.stream(
        "POST",
        "/v1/chat/stream",
        json={"message": "hola"},
        headers={"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"},
    ) as resp:
        assert resp.status_code == 200


class _CrashAgent:
    async def start_session(self, title: str | None = None) -> uuid.UUID:
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
    ) -> LoopResult:
        raise RuntimeError("sdk blew up")


@pytest.fixture
async def crash_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent] = _CrashAgent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_chat_stream_maps_unexpected_error_to_sse_event(
    crash_client: httpx.AsyncClient,
) -> None:
    body = ""
    async with crash_client.stream(
        "POST", "/v1/chat/stream", json={"message": "hi"}
    ) as resp:
        assert resp.status_code == 200
        async for chunk in resp.aiter_text():
            body += chunk

    # The client gets a clean error event — never a half-broken stream.
    assert "event: error" in body
    assert "Something went wrong" in body
    # The internal detail is not leaked to the caller.
    assert "sdk blew up" not in body


class _ToolAgent:
    async def start_session(self, title: str | None = None) -> uuid.UUID:
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
    ) -> LoopResult:
        assert observer is not None
        observer(
            "tool",
            {
                "tool": "get_order",
                "args": {"order_id": "ord_0001"},
                "output": "status: active",
            },
        )
        observer("text", {"delta": "listo"})
        return LoopResult(reply="listo", iterations=2)


@pytest.fixture
async def tool_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent] = _ToolAgent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_chat_stream_surfaces_tool_calls(tool_client: httpx.AsyncClient) -> None:
    body = ""
    async with tool_client.stream(
        "POST", "/v1/chat/stream", json={"message": "estado de ord_0001?"}
    ) as resp:
        assert resp.status_code == 200
        async for chunk in resp.aiter_text():
            body += chunk

    # the tool call is visible in the stream: name + args + result preview...
    assert "event: tool" in body
    assert "get_order" in body
    assert "ord_0001" in body
    # ...and the final answer still streams and closes with done
    assert "event: delta" in body
    assert "event: done" in body
