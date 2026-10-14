"""Contract tests for POST /v1/auth/session (service/api/v1/auth.py).

The Firebase verifier is faked (its own checks are unit-tested in
test_host_token.py); what's under test here is the exchange: a verified host
identity becomes a session token that get_principal accepts, and every
failure maps to the right status without leaking why.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from service.api.v1.auth import get_host_verifier
from service.core import session_token
from service.core.config import Settings, get_settings
from service.core.host_token import HostIdentity, InvalidHostToken
from service.main import create_app

_KEY = "test-signing-key-with-enough-entropy-0123456789"
_GOOD = "good-host-token"


class _FakeVerifier:
    def verify(self, token: str) -> HostIdentity:
        if token != _GOOD:
            raise InvalidHostToken("bad")
        return HostIdentity(
            uid="firebase-uid-1",
            email="aliado@example.com",
            merchant_id="42",
            store_id="7",
            role="admin",
        )


def _settings(**overrides: str) -> Callable[[], Settings]:
    values = {
        "ENVIRONMENT": "dev",
        "FIREBASE_PROJECT_ID": "cashea-web-app-stg",
        "SESSION_SIGNING_KEY": _KEY,
        **overrides,
    }
    return lambda: Settings(**values)


def _client(settings: Callable[[], Settings]) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_settings] = settings
    app.dependency_overrides[get_host_verifier] = _FakeVerifier
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(_settings()) as c:
        yield c


async def test_exchanges_a_valid_host_token_for_a_session_token(
    api: httpx.AsyncClient,
) -> None:
    resp = await api.post("/v1/auth/session", json={"host_token": _GOOD})

    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 900
    assert body["email"] == "aliado@example.com"
    principal = session_token.verify(body["session_token"], _KEY)
    assert principal.user_id == "firebase-uid-1"
    assert principal.merchant_id == "42"
    assert principal.store_id == "7"
    assert principal.role == "admin"


async def test_invalid_host_token_is_401(api: httpx.AsyncClient) -> None:
    resp = await api.post("/v1/auth/session", json={"host_token": "forged"})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid host token."}


async def test_empty_host_token_is_rejected_at_the_boundary(
    api: httpx.AsyncClient,
) -> None:
    resp = await api.post("/v1/auth/session", json={"host_token": ""})

    assert resp.status_code == 422


@pytest.mark.parametrize("missing", ["FIREBASE_PROJECT_ID", "SESSION_SIGNING_KEY"])
async def test_unconfigured_service_refuses_instead_of_issuing(missing: str) -> None:
    async with _client(_settings(**{missing: ""})) as c:
        resp = await c.post("/v1/auth/session", json={"host_token": _GOOD})

    assert resp.status_code == 503
