"""Contract tests for POST /v1/chat (Level 1 — deterministic, no network, no DB).

The ``get_agent`` dependency is overridden with a fake Agent, so these exercise
the HTTP contract — request validation, response shape, session handling, error
mapping — without a database or an LLM. The real end-to-end turn (respond over a
real Postgres) is covered by ``tests/integration/test_respond.py``.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import AsyncIterator

import anthropic
import httpx
import pytest

from agent.identity import Principal
from agent.loop.agent import LoopResult
from agent.observability import Observer
from agent.vision import Image
from service.core.agent import get_agent
from service.main import create_app

_SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# A real (tiny, 2x2 red) PNG — the magic-number check in
# ImageInput._validate_base64_and_size rejects anything that doesn't actually
# look like its declared media_type, so "valid image" test fixtures need real
# bytes, not an arbitrary base64 string.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7"
    "gP9i18U1AAAAABJRU5ErkJggg=="
)


class _FakeAgent:
    # No constructor params: this class is used directly as a FastAPI
    # dependency-override callable (`dependency_overrides[get_agent] =
    # _FakeAgent`) in most tests, so FastAPI's own DI would introspect and
    # try to satisfy any `__init__` parameter as if it were a request field —
    # tests that need custom `segments` set the attribute after construction
    # instead (see test_chat_surfaces_a_pending_choice_in_the_response).
    def __init__(self) -> None:
        self.received_principal: Principal | None = None
        self.received_images: list[Image] | None = None
        self.received_choice_id: str | None = None
        self.start_session_principal: Principal | None = None
        self.segments: list[dict[str, object]] = []

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
        return LoopResult(reply="hi from fake", iterations=1, segments=self.segments)


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


async def test_chat_accepts_identity_headers(chat_client: httpx.AsyncClient) -> None:
    # Dev-only stub (service/core/identity.py) — the route must accept the
    # headers without erroring.
    resp = await chat_client.post(
        "/v1/chat",
        json={"message": "hello"},
        headers={"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"},
    )

    assert resp.status_code == 200


async def test_chat_forwards_the_resolved_principal_to_respond() -> None:
    """The route must not just log the header — the resolved Principal has to
    reach `Agent.respond`, since that's what threads it into the loop/tools."""
    app = create_app()
    agent = _FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/v1/chat",
            json={"message": "hello"},
            headers={"X-User-Id": "usr_0001", "X-User-Email": "alice@example.com"},
        )

    assert resp.status_code == 200
    expected = Principal(user_id="usr_0001", email="alice@example.com")
    assert agent.received_principal == expected
    # A brand-new conversation must also be tagged with its owner at creation.
    assert agent.start_session_principal == expected


async def test_chat_forwards_no_principal_when_headers_are_absent() -> None:
    app = create_app()
    agent = _FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/v1/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert agent.received_principal is None


async def test_chat_rejects_empty_message(chat_client: httpx.AsyncClient) -> None:
    # Validation at the boundary: Field(min_length=1) → 422, the agent never runs.
    resp = await chat_client.post("/v1/chat", json={"message": ""})

    assert resp.status_code == 422


async def test_chat_forwards_a_valid_image_to_respond() -> None:
    app = create_app()
    agent = _FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/v1/chat",
            json={
                "message": "aquí está mi comprobante",
                "images": [{"media_type": "image/png", "data": _TINY_PNG_B64}],
            },
        )

    assert resp.status_code == 200
    assert agent.received_images == [Image(media_type="image/png", data=_TINY_PNG_B64)]


async def test_chat_rejects_a_malformed_base64_image(
    chat_client: httpx.AsyncClient,
) -> None:
    # Validation at the boundary: bad base64 must 422 before it ever reaches
    # the LLM call, not surface as an opaque provider error mid-turn.
    resp = await chat_client.post(
        "/v1/chat",
        json={
            "message": "hola",
            "images": [{"media_type": "image/png", "data": "not-valid-base64!!!"}],
        },
    )

    assert resp.status_code == 422


async def test_chat_rejects_an_oversized_image(chat_client: httpx.AsyncClient) -> None:
    oversized = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
    resp = await chat_client.post(
        "/v1/chat",
        json={
            "message": "hola",
            "images": [{"media_type": "image/png", "data": oversized}],
        },
    )

    assert resp.status_code == 422


async def test_chat_rejects_a_data_string_longer_than_the_base64_cap(
    chat_client: httpx.AsyncClient,
) -> None:
    """`Field(max_length=_MAX_IMAGE_BASE64_CHARS)` must reject an oversized
    `data` string by its encoded length alone, before the field_validator ever
    calls `base64.b64decode` on it — the fix for a request that could
    otherwise force a full decode of an attacker-supplied multi-GB string
    before any size check ran (see _MAX_IMAGE_BASE64_CHARS in
    service/api/v1/chat.py)."""
    from service.api.v1.chat import _MAX_IMAGE_BASE64_CHARS

    oversized = "x" * (_MAX_IMAGE_BASE64_CHARS + 1)
    resp = await chat_client.post(
        "/v1/chat",
        json={
            "message": "hola",
            "images": [{"media_type": "image/png", "data": oversized}],
        },
    )

    assert resp.status_code == 422
    # Rejected by the length cap itself — the custom base64 validator (whose
    # errors mention "base64") never even ran.
    assert "base64" not in resp.text


async def test_chat_rejects_a_mismatched_media_type(
    chat_client: httpx.AsyncClient,
) -> None:
    # "hello", base64-encoded, declared as a PNG: valid base64, well under the
    # size limit, but not remotely a PNG — the magic-number check must catch
    # a mislabeled (or non-image) payload the earlier checks let through.
    resp = await chat_client.post(
        "/v1/chat",
        json={
            "message": "hola",
            "images": [{"media_type": "image/png", "data": "aGVsbG8="}],
        },
    )

    assert resp.status_code == 422


async def test_chat_rejects_both_message_and_choice_id(
    chat_client: httpx.AsyncClient,
) -> None:
    resp = await chat_client.post(
        "/v1/chat",
        json={
            "message": "hello",
            "choice_id": "card",
            "session_id": str(_SESSION_ID),
        },
    )

    assert resp.status_code == 422


async def test_chat_rejects_neither_message_nor_choice_id(
    chat_client: httpx.AsyncClient,
) -> None:
    resp = await chat_client.post("/v1/chat", json={})

    assert resp.status_code == 422


async def test_chat_rejects_choice_id_without_a_session_id(
    chat_client: httpx.AsyncClient,
) -> None:
    """There's no pending choice without an existing conversation to check."""
    resp = await chat_client.post("/v1/chat", json={"choice_id": "card"})

    assert resp.status_code == 422


async def test_chat_forwards_choice_id_to_respond() -> None:
    app = create_app()
    agent = _FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/v1/chat",
            json={"choice_id": "card", "session_id": str(_SESSION_ID)},
        )

    assert resp.status_code == 200
    assert agent.received_choice_id == "card"


async def test_chat_surfaces_a_pending_choice_in_the_response() -> None:
    """When a turn suspends, the response's `choice` field carries what to
    render — the client shouldn't have to parse `segments` itself."""
    app = create_app()
    choice_segment: dict[str, object] = {
        "type": "choice",
        "prompt": "¿Reembolso o crédito?",
        "options": [{"id": "card", "label": "Tarjeta"}],
    }
    agent = _FakeAgent()
    agent.segments = [choice_segment]
    app.dependency_overrides[get_agent] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/v1/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert resp.json()["choice"] == {
        "prompt": "¿Reembolso o crédito?",
        "options": [{"id": "card", "label": "Tarjeta"}],
    }


async def test_chat_response_has_no_choice_field_for_an_ordinary_turn(
    chat_client: httpx.AsyncClient,
) -> None:
    resp = await chat_client.post("/v1/chat", json={"message": "hello"})

    assert resp.json()["choice"] is None


async def test_chat_rejects_more_images_than_the_per_turn_limit(
    chat_client: httpx.AsyncClient,
) -> None:
    image = {"media_type": "image/png", "data": _TINY_PNG_B64}
    resp = await chat_client.post(
        "/v1/chat", json={"message": "hola", "images": [image] * 5}
    )

    assert resp.status_code == 422


class _BoomAgent:
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
