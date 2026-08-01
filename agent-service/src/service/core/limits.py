"""Request-body size limit — enforced before FastAPI/Starlette ever reads the
body into memory.

Pydantic's own ``Field(max_length=...)`` (see ``service/api/v1/chat.py``)
only runs AFTER the whole request body has been read off the socket and
JSON-parsed into a Python object — a request that could never pass that
validation still forces that full read/parse first. This middleware rejects
an oversized body at the ASGI boundary, before any of that happens.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.responses import JSONResponse

# MutableMapping, matching Starlette/ASGI's own scope typing — a plain `dict`
# is invariant enough that `ASGITransport`/Starlette's ASGI protocol rejects it.
Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

# Comfortably covers the largest legitimate request today (4 images at
# ImageInput's own 5MB-per-image cap, base64-inflated ~4/3, plus JSON
# overhead — see _MAX_IMAGE_BASE64_CHARS in service/api/v1/chat.py) with
# headroom, while still bounding worst-case memory per request. Also happens
# to match Cloud Run's own default max request size (32MB).
MAX_BODY_BYTES = 32 * 1024 * 1024


class MaxBodySizeMiddleware:
    """Raw ASGI middleware (not `BaseHTTPMiddleware`, which buffers the whole
    body itself before a handler ever sees it — exactly what this needs to
    avoid). Rejects via the declared `Content-Length` header, which every
    real client sends for a JSON POST body; a request that lies about it
    (no header, or an understated one) is caught as the body is actually
    read, before it's handed to the application.
    """

    def __init__(self, app: Any, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = next(
            (v for k, v in scope.get("headers", []) if k == b"content-length"), None
        )
        if content_length is not None and int(content_length) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        seen = 0

        async def guarded_receive() -> MutableMapping[str, Any]:
            nonlocal seen
            message = await receive()
            seen += len(message.get("body") or b"")
            if seen > self.max_bytes:
                raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, guarded_receive, send)
        except _BodyTooLarge:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"detail": "Request body too large."}, status_code=413)
        await response(scope, receive, send)


class _BodyTooLarge(Exception):
    """Internal signal only — never escapes this module."""
