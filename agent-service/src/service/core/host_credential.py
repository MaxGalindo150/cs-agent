"""The aliado's own token, for merchant tools that read Cashea's API as them.

The embedded widget sends a fresh Firebase ID token from the host
(``X-Host-Token``) on chat calls only. It is accepted only for a verified
aliado and only if it belongs to the same user as their session token — so a
session can never borrow someone else's credentials. A bad, expired or
mismatched one is a 401, the same signal the widget already handles by
renewing; it is never silently dropped or used.

The token is handed to the agent for this turn (``ToolContext.host_credential``)
and nowhere else: not stored, not logged, not traced.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import Depends, Header, HTTPException, Request, status

from agent.identity import Principal, audience_of
from service.core.host_token import InvalidHostToken, get_host_verifier
from service.core.identity import get_principal

log = structlog.get_logger()


async def get_host_credential(
    request: Request,
    principal: Principal | None = Depends(get_principal),
    x_host_token: str | None = Header(default=None, alias="X-Host-Token"),
) -> str | None:
    if not x_host_token:
        return None
    if principal is None or audience_of(principal) != "merchant":
        # Only aliados' turns use it; anyone else has no business sending one.
        log.info("host_credential.ignored", reason="not an aliado")
        return None
    # Looked up only now, so turns without the header need no verifier.
    verifier = get_host_verifier(request)
    try:
        host = await asyncio.to_thread(verifier.verify, x_host_token)
    except InvalidHostToken:
        raise _unauthorized() from None
    if host.uid != principal.user_id:
        log.warning("host_credential.user_mismatch", user_id=principal.user_id)
        raise _unauthorized()
    return x_host_token


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid host token.")
