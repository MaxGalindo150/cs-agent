"""Exchange the host app's token for a widget session token.

The embedded widget calls this on first send and whenever its session token
expires: it gets a fresh Firebase ID token from the host (merchant-web's
``getToken``), posts it here once, and from then on sends only the session
token it gets back (see service/core/session_token.py for why two tokens).
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent.identity import Principal
from service.core import session_token
from service.core.config import Settings, get_settings
from service.core.host_token import FirebaseTokenVerifier, InvalidHostToken

log = structlog.get_logger()

router = APIRouter(tags=["auth"])


class SessionRequest(BaseModel):
    # Firebase ID tokens are ~1KB; the cap only stops abuse.
    host_token: str = Field(min_length=1, max_length=8192)


class SessionResponse(BaseModel):
    session_token: str
    expires_in: int
    email: str | None


def get_host_verifier(request: Request) -> FirebaseTokenVerifier:
    """Dependency: the process-wide verifier (it caches Google's keys)."""
    verifier: FirebaseTokenVerifier = request.app.state.host_verifier
    return verifier


@router.post("/auth/session", response_model=SessionResponse)
async def create_session(
    req: SessionRequest,
    settings: Settings = Depends(get_settings),
    verifier: FirebaseTokenVerifier = Depends(get_host_verifier),
) -> SessionResponse:
    if not settings.firebase_project_id or not settings.session_signing_key:
        log.error("auth.session.not_configured")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Host sign-in is not configured."
        )

    try:
        # Off the event loop: verifying may fetch Google's public keys.
        host = await asyncio.to_thread(verifier.verify, req.host_token)
    except InvalidHostToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid host token."
        ) from None

    principal = Principal(
        user_id=host.uid,
        email=host.email,
        merchant_id=host.merchant_id,
        store_id=host.store_id,
        role=host.role,
    )
    log.info(
        "auth.session.issued",
        user_id=principal.user_id,
        merchant_id=principal.merchant_id,
    )
    return SessionResponse(
        session_token=session_token.issue(
            principal, settings.session_signing_key, settings.session_ttl_seconds
        ),
        expires_in=settings.session_ttl_seconds,
        email=principal.email,
    )
