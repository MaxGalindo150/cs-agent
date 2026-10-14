"""Unit tests for Firebase host-token verification (service/core/host_token.py).

Tokens are signed here with a throwaway RSA key standing in for Google's, and
the verifier is handed a fake key client — no network, no real Firebase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from service.core.host_token import FirebaseTokenVerifier, InvalidHostToken

_PROJECT = "cashea-web-app-stg"
_GOOGLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class _SigningKey:
    key: Any


class _FakeJwks:
    """Always answers with Google's (test) public key, like PyJWKClient would
    for a token whose `kid` it knows."""

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return _SigningKey(_GOOGLE_KEY.public_key())


def _verifier(project_id: str = _PROJECT) -> FirebaseTokenVerifier:
    return FirebaseTokenVerifier(project_id, jwks_client=_FakeJwks())  # type: ignore[arg-type]


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": f"https://securetoken.google.com/{_PROJECT}",
        "aud": _PROJECT,
        "sub": "firebase-uid-1",
        "iat": now - 10,
        "exp": now + 3600,
        "auth_time": now - 60,
        "email": "aliado@example.com",
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _sign(claims: dict[str, Any], key: Any = _GOOGLE_KEY, alg: str = "RS256") -> str:
    return jwt.encode(claims, key, algorithm=alg)


def test_valid_token_yields_the_firebase_identity() -> None:
    host = _verifier().verify(_sign(_claims()))

    assert host.uid == "firebase-uid-1"
    assert host.email == "aliado@example.com"


@pytest.mark.parametrize(
    "token",
    [
        _sign(_claims(aud="another-project")),
        _sign(_claims(iss="https://securetoken.google.com/another-project")),
        _sign(_claims(exp=int(time.time()) - 3600)),
        _sign(_claims(auth_time=int(time.time()) + 3600)),
        _sign(_claims(auth_time=None)),
        _sign(_claims(sub="")),
        _sign(_claims(), key=_OTHER_KEY),
        _sign(_claims(), key="a-shared-secret-instead-of-rsa-0123456789", alg="HS256"),
        "not-a-jwt",
    ],
    ids=[
        "wrong-audience",
        "wrong-issuer",
        "expired",
        "future-auth-time",
        "missing-auth-time",
        "empty-sub",
        "forged-signature",
        "hs256-algorithm",
        "garbage",
    ],
)
def test_rejects(token: str) -> None:
    with pytest.raises(InvalidHostToken):
        _verifier().verify(token)


def test_rejects_everything_when_no_project_is_configured() -> None:
    with pytest.raises(InvalidHostToken):
        _verifier(project_id="").verify(_sign(_claims()))
