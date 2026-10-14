"""Identity seam: where a verified end-user arrives from the transport.

Resolution order:

1. ``Authorization: Bearer <session token>`` — issued by ``POST
   /v1/auth/session`` after verifying the host app's Firebase token (the
   embedded widget). Verified here; an invalid or expired one is a 401, never
   a silent fall back to anonymous, so the widget knows to renew.
2. Dev only: the ``X-User-Id``/``X-User-Email`` headers, trusted verbatim.
   Kept for the demo page's simulated login (frontend lib/identity/). Outside
   ``settings.is_development`` they are ignored.
3. Otherwise ``None`` — an anonymous visitor.

The shape (``-> Principal | None``) is what routes and the agent layer depend
on; how it was resolved never leaks past this function.

Security notes: see ``docs/SECURITY.md``.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from agent.identity import Principal
from service.core import session_token
from service.core.config import Settings, get_settings

_USER_ID_HEADER = "X-User-Id"
_USER_EMAIL_HEADER = "X-User-Email"


def get_principal(
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias=_USER_ID_HEADER),
    x_user_email: str | None = Header(default=None, alias=_USER_EMAIL_HEADER),
) -> Principal | None:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized()
        try:
            return session_token.verify(token, settings.session_signing_key)
        except session_token.InvalidSessionToken:
            raise _unauthorized() from None

    if settings.is_development and x_user_id:
        return Principal(user_id=x_user_id, email=x_user_email)
    return None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired session token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
