"""Contract test for the *registration order* of app-level middleware
(service/main.py::create_app).

`MaxBodySizeMiddleware` must sit inside `CORSMiddleware` — otherwise its 413
short-circuit bypasses CORS, and a cross-origin browser caller sees an opaque
CORS failure instead of a readable 413 (fetch/XHR never surfaces the status
or body when the response is missing the CORS headers the browser expects).

This drives `create_app()` itself, not a hand-composed stand-in — a
regression that flips the two `app.add_middleware(...)` calls in main.py
fails this test, which a test only composing the two middlewares directly
(tests/unit/test_limits.py) cannot catch.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from service.main import create_app

# Must match a real entry in Settings.allowed_origins (service/core/config.py)
# for CORSMiddleware to echo it back.
_ORIGIN = "http://localhost:3000"


async def test_an_oversized_request_413s_with_cors_headers_intact() -> None:
    """A declared Content-Length far over the cap is enough to trip the 413
    — no need to actually send 32MB+ of body bytes."""
    app = create_app()
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    scope: MutableMapping[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat",
        "raw_path": b"/v1/chat",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(40 * 1024 * 1024).encode()),
            (b"origin", _ORIGIN.encode()),
        ],
        "client": ("testclient", 1234),
        "server": ("testserver", 80),
        "state": {},
    }

    await app(scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 413
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    assert headers["access-control-allow-origin"] == _ORIGIN
