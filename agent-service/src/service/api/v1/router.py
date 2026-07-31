"""Aggregate router for the versioned (v1) API.

`main.py` mounts this single router; each endpoint module registers its routes
here under the `/v1` prefix. Wiring a new v1 endpoint never touches `main.py`.
"""

from __future__ import annotations

from fastapi import APIRouter

from service.api.v1.chat import router as chat_router
from service.api.v1.chat_stream import router as chat_stream_router
from service.api.v1.sessions import router as sessions_router

router = APIRouter(prefix="/v1")
router.include_router(chat_router)
router.include_router(chat_stream_router)
router.include_router(sessions_router)
