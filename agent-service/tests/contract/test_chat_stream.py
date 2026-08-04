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

from agent.identity import Principal
from agent.loop.agent import LoopResult
from agent.observability import Observer
from agent.vision import Image
from service.core.agent import get_agent
from service.main import create_app

_SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

# A real (tiny, 2x2 red) PNG — see tests/contract/test_chat.py for why a
# "valid image" fixture needs real bytes, not an arbitrary base64 string.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7"
    "gP9i18U1AAAAABJRU5ErkJggg=="
)


class _StreamAgent:
    def __init__(self) -> None:
        self.received_principal: Principal | None = None
        self.received_images: list[Image] | None = None
        self.received_choice_id: str | None = None
        self.start_session_principal: Principal | None = None
        self.needs_human: bool = False

    async def start_session(
        self, title: str | None = None, principal: Principal | None = None
    ) -> uuid.UUID:
        self.start_session_principal = principal
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str | None = None,
        choice_id: str | None = None,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
        principal: Principal | None = None,
        images: list[Image] | None = None,
    ) -> LoopResult:
        self.received_principal = principal
        self.received_images = images
        self.received_choice_id = choice_id
        assert observer is not None
        observer("text", {"delta": "Hola"})
        observer("text", {"delta": " mundo"})
        return LoopResult(
            reply="Hola mundo", iterations=1, needs_human=self.needs_human
        )


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


async def test_chat_stream_done_event_carries_needs_human() -> None:
    """A budget-exhausted resume (or an already-escalated session) looks like
    an ordinary reply otherwise — `done`'s `needs_human` field is the only
    machine-readable signal a streaming client has to tell them apart."""
    app = create_app()
    agent = _StreamAgent()
    agent.needs_human = True
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    body = ""
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async with c.stream(
            "POST", "/v1/chat/stream", json={"message": "hola"}
        ) as resp:
            assert resp.status_code == 200
            async for chunk in resp.aiter_text():
                body += chunk

    assert "event: done" in body
    assert '"needs_human": true' in body


async def test_chat_stream_accepts_identity_headers(
    stream_client: httpx.AsyncClient,
) -> None:
    # Dev-only stub (service/core/identity.py) — the route must accept the
    # headers without erroring.
    async with stream_client.stream(
        "POST",
        "/v1/chat/stream",
        json={"message": "hola"},
        headers={"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"},
    ) as resp:
        assert resp.status_code == 200


async def test_chat_stream_forwards_the_resolved_principal_to_respond() -> None:
    """Same contract as /v1/chat: the resolved Principal must reach
    `Agent.respond`, not just get logged."""
    app = create_app()
    agent = _StreamAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async with c.stream(
            "POST",
            "/v1/chat/stream",
            json={"message": "hola"},
            headers={"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"},
        ) as resp:
            assert resp.status_code == 200
            async for _ in resp.aiter_text():
                pass

    expected = Principal(user_id="usr_0001", email="alice@example.com")
    assert agent.received_principal == expected
    assert agent.start_session_principal == expected


async def test_chat_stream_forwards_a_valid_image_to_respond() -> None:
    """Same contract as /v1/chat: an attached image must reach
    `Agent.respond`, not get dropped by the streaming path's `images=images`
    wiring in `chat_stream()`."""
    app = create_app()
    agent = _StreamAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async with c.stream(
            "POST",
            "/v1/chat/stream",
            json={
                "message": "aquí está mi comprobante",
                "images": [{"media_type": "image/png", "data": _TINY_PNG_B64}],
            },
        ) as resp:
            assert resp.status_code == 200
            async for _ in resp.aiter_text():
                pass

    assert agent.received_images == [Image(media_type="image/png", data=_TINY_PNG_B64)]


async def test_chat_stream_rejects_both_message_and_choice_id(
    stream_client: httpx.AsyncClient,
) -> None:
    resp = await stream_client.post(
        "/v1/chat/stream",
        json={"message": "hola", "choice_id": "card", "session_id": str(_SESSION_ID)},
    )

    assert resp.status_code == 422


async def test_chat_stream_rejects_choice_id_without_a_session_id(
    stream_client: httpx.AsyncClient,
) -> None:
    resp = await stream_client.post("/v1/chat/stream", json={"choice_id": "card"})

    assert resp.status_code == 422


async def test_chat_stream_forwards_choice_id_to_respond() -> None:
    app = create_app()
    agent = _StreamAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async with c.stream(
            "POST",
            "/v1/chat/stream",
            json={"choice_id": "card", "session_id": str(_SESSION_ID)},
        ) as resp:
            assert resp.status_code == 200
            async for _ in resp.aiter_text():
                pass

    assert agent.received_choice_id == "card"


class _ChoiceAgent:
    async def start_session(
        self, title: str | None = None, principal: Principal | None = None
    ) -> uuid.UUID:
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str | None = None,
        choice_id: str | None = None,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
        principal: Principal | None = None,
        images: list[Image] | None = None,
    ) -> LoopResult:
        assert observer is not None
        observer(
            "choice",
            {
                "prompt": "¿Reembolso o crédito?",
                "options": [{"id": "card", "label": "Tarjeta"}],
            },
        )
        return LoopResult(reply="¿Reembolso o crédito?", iterations=1)


@pytest.fixture
async def choice_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent] = _ChoiceAgent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_chat_stream_surfaces_a_choice_event(
    choice_client: httpx.AsyncClient,
) -> None:
    body = ""
    async with choice_client.stream(
        "POST", "/v1/chat/stream", json={"message": "quiero mi reembolso"}
    ) as resp:
        assert resp.status_code == 200
        async for chunk in resp.aiter_text():
            body += chunk

    assert "event: choice" in body
    assert "Tarjeta" in body
    # the stream still closes normally — the client resumes on its own terms,
    # not because the connection stayed open waiting for an answer
    assert "event: done" in body


class _CrashAgent:
    async def start_session(
        self, title: str | None = None, principal: Principal | None = None
    ) -> uuid.UUID:
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str | None = None,
        choice_id: str | None = None,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
        principal: Principal | None = None,
        images: list[Image] | None = None,
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
    async def start_session(
        self, title: str | None = None, principal: Principal | None = None
    ) -> uuid.UUID:
        return _SESSION_ID

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str | None = None,
        choice_id: str | None = None,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
        principal: Principal | None = None,
        images: list[Image] | None = None,
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
