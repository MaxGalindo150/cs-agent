"""Unit tests for the request-body size guard (service/core/limits.py).

A tiny in-test ASGI app + a small `max_bytes` cap, so these exercise the
middleware itself in isolation — no FastAPI app, no real 32MB payload.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, MutableMapping
from typing import Any

import httpx
from starlette.middleware.cors import CORSMiddleware

from service.core.limits import MaxBodySizeMiddleware


async def _echo_app(
    scope: dict[str, Any],
    receive: Any,
    send: Any,
) -> None:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def test_a_body_within_the_cap_passes_through() -> None:
    app = MaxBodySizeMiddleware(_echo_app, max_bytes=16)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/", content=b"short")

    assert resp.status_code == 200
    assert resp.content == b"short"


async def test_a_content_length_over_the_cap_is_rejected_before_the_body_is_read() -> (
    None
):
    app = MaxBodySizeMiddleware(_echo_app, max_bytes=16)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/", content=b"x" * 32)

    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large."}


async def test_a_chunked_body_over_the_cap_is_rejected_sans_content_length() -> None:
    """No declared Content-Length (httpx sends chunked transfer encoding for a
    streamed body) — must still be caught as bytes are actually read, via
    `guarded_receive`'s running count, not just the header pre-check."""

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(4):
            yield b"x" * 10  # 40 bytes total, over the 16-byte cap

    app = MaxBodySizeMiddleware(_echo_app, max_bytes=16)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/", content=chunks())

    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large."}


async def test_a_413_still_carries_cors_headers_when_cors_wraps_us() -> None:
    """`service/main.py::create_app` must register this middleware *inside*
    CORSMiddleware — this proves the mechanism (a 413 raised from here still
    passes back out through an outer CORS layer). The registration itself is
    guarded separately, against the real app, by
    tests/contract/test_middleware_order.py — a hand-composed stand-in like
    this one can't catch main.py's registration order flipping back."""
    inner = MaxBodySizeMiddleware(_echo_app, max_bytes=16)
    app = CORSMiddleware(inner, allow_origins=["http://localhost:3000"])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/", content=b"x" * 32, headers={"Origin": "http://localhost:3000"}
        )

    assert resp.status_code == 413
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_a_non_http_scope_passes_straight_through() -> None:
    """Lifespan/websocket scopes must never be size-guarded — only `http`."""
    seen: list[dict[str, Any]] = []

    async def lifespan_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        seen.append(scope)

    app = MaxBodySizeMiddleware(lifespan_app, max_bytes=16)

    async def receive() -> MutableMapping[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(message: MutableMapping[str, Any]) -> None:
        pass

    await app({"type": "lifespan"}, receive, send)

    assert seen == [{"type": "lifespan"}]
