"""Contract tests for POST /v1/chat (Level 1 — deterministic, no network, no DB).

The ``get_agent`` dependency is overridden with a fake Agent, so these exercise
the HTTP contract — request validation, response shape, session handling, error
mapping — without a database or an LLM. The real end-to-end turn (respond over a
real Postgres) is covered by ``tests/integration/test_respond.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import anthropic
import httpx
import pytest

from agent.loop.agent import LoopResult
from agent.observability import Observer
from service.core.agent import get_agent
from service.main import create_app

_SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _FakeAgent:
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
        return LoopResult(reply="hi from fake", iterations=1)


@pytest.fixture
async def chat_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent] = _FakeAgent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_chat_returns_a_reply_and_the_session_id(
    chat_client: httpx.AsyncClient,
) -> None:
    resp = await chat_client.post("/v1/chat", json={"message": "hello"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "hi from fake"
    assert body["iterations"] == 1
    # a new conversation → the minted id comes back so the client can continue
    assert body["session_id"] == str(_SESSION_ID)


async def test_chat_rejects_empty_message(chat_client: httpx.AsyncClient) -> None:
    # Validation at the boundary: Field(min_length=1) → 422, the agent never runs.
    resp = await chat_client.post("/v1/chat", json={"message": ""})

    assert resp.status_code == 422


class _BoomAgent:
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
        raise anthropic.APIError(
            "upstream boom", httpx.Request("POST", "http://test"), body=None
        )


@pytest.fixture
async def boom_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent] = _BoomAgent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_chat_maps_provider_error_to_clean_502(
    boom_client: httpx.AsyncClient,
) -> None:
    resp = await boom_client.post("/v1/chat", json={"message": "hello"})

    assert resp.status_code == 502
    assert resp.json() == {"detail": "The assistant is temporarily unavailable."}
    # the upstream detail is logged server-side, never leaked to the caller
    assert "boom" not in resp.text
