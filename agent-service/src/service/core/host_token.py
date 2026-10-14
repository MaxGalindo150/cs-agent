"""Verify the host app's Firebase ID token — the credential merchant-web hands
the embedded widget through ``casheaChat.init({ getToken })``.

Checked exactly as Firebase documents for third-party verification: RS256,
signed by one of Google's ``securetoken`` keys, ``aud`` = the project id,
``iss`` = ``https://securetoken.google.com/<project id>``, unexpired, issued
and authenticated in the past, non-empty ``sub``. Anything else is rejected
with ``InvalidHostToken``; the reason is logged but never returned to the
caller.

The token is only read here, to mint this service's own session token
(service/core/session_token.py). It is never stored or logged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt
import structlog

log = structlog.get_logger()

_GOOGLE_JWKS_URL = (
    "https://www.googleapis.com/service_accounts/v1/jwk/"
    "securetoken@system.gserviceaccount.com"
)
# Tolerance for clock drift between Google and this host.
_LEEWAY_SECONDS = 30


class InvalidHostToken(Exception):
    """The host token is missing, malformed, forged, expired or for another project."""


@dataclass(frozen=True, slots=True)
class HostIdentity:
    """What a verified Firebase token says about the caller. Who they are at
    Cashea (merchant, store, role) is not in the token — merchant-web sets no
    such claims; see service/core/merchant_directory.py."""

    uid: str
    email: str | None


class FirebaseTokenVerifier:
    def __init__(
        self, project_id: str, jwks_client: jwt.PyJWKClient | None = None
    ) -> None:
        self._project_id = project_id
        # PyJWKClient caches Google's keys and refetches on an unknown `kid`
        # (Google rotates them), so one instance lives for the process.
        self._jwks = jwks_client or jwt.PyJWKClient(_GOOGLE_JWKS_URL, cache_keys=True)

    def verify(self, token: str) -> HostIdentity:
        """Blocking (may fetch Google's keys) — call it off the event loop."""
        if not self._project_id:
            raise InvalidHostToken("FIREBASE_PROJECT_ID is not configured")
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._project_id,
                issuer=f"https://securetoken.google.com/{self._project_id}",
                leeway=_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "auth_time"]},
            )
        except jwt.PyJWTError as exc:
            log.info("host_token.rejected", reason=type(exc).__name__)
            raise InvalidHostToken(str(exc)) from exc

        if not claims["sub"]:
            raise InvalidHostToken("empty sub")
        if claims["auth_time"] > time.time() + _LEEWAY_SECONDS:
            raise InvalidHostToken("auth_time is in the future")

        return HostIdentity(uid=claims["sub"], email=claims.get("email"))
