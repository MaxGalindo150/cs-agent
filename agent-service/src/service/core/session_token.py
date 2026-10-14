"""This service's own short-lived session token for the embedded widget.

Issued by ``POST /v1/auth/session`` once a host token has been verified
(service/core/host_token.py), then sent as ``Authorization: Bearer`` on every
chat call and checked by ``get_principal``. A separate token, rather than
re-sending the Firebase one, means the host credential crosses into this
service once per renewal and is never held anywhere afterwards.

HS256 with ``SESSION_SIGNING_KEY``: only this service issues and reads these,
so a shared secret is enough. ``iss``/``aud`` pin them to this purpose.
"""

from __future__ import annotations

import time
from typing import Any

import jwt

from agent.identity import Principal

_ISSUER = "cs-agent"
_AUDIENCE = "cs-agent-widget"


class InvalidSessionToken(Exception):
    """Missing key, bad signature, wrong issuer/audience, or expired."""


def issue(principal: Principal, signing_key: str, ttl_seconds: int) -> str:
    if not signing_key:
        raise InvalidSessionToken("SESSION_SIGNING_KEY is not configured")
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
        "sub": principal.user_id,
        "email": principal.email,
        "merchant_id": principal.merchant_id,
        "merchant_name": principal.merchant_name,
        "store_id": principal.store_id,
        "store_uuid": principal.store_uuid,
        "store_name": principal.store_name,
        "role": principal.role,
    }
    return jwt.encode(claims, signing_key, algorithm="HS256")


def verify(token: str, signing_key: str) -> Principal:
    if not signing_key:
        raise InvalidSessionToken("SESSION_SIGNING_KEY is not configured")
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            audience=_AUDIENCE,
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidSessionToken(str(exc)) from exc
    return Principal(
        user_id=claims["sub"],
        email=claims.get("email"),
        merchant_id=claims.get("merchant_id"),
        merchant_name=claims.get("merchant_name"),
        store_id=claims.get("store_id"),
        store_uuid=claims.get("store_uuid"),
        store_name=claims.get("store_name"),
        role=claims.get("role"),
    )
