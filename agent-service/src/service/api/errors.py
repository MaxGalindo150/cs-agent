"""Central exception handlers: turn provider failures into clean responses.

An upstream LLM error (bad key, rate limit, 5xx from the provider) is not our
bug and must never leak a stack trace or provider detail to the caller. We log
the detail server-side and return a controlled 502 — the service itself is
healthy; the dependency failed.
"""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()


async def handle_provider_error(request: Request, exc: Exception) -> JSONResponse:
    """Handle any `anthropic.APIError`: log it, return an opaque 502."""
    log.error("llm.provider_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=502,
        content={"detail": "The assistant is temporarily unavailable."},
    )
