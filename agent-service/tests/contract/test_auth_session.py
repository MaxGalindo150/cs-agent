"""Contract tests for POST /v1/auth/session (service/api/v1/auth.py).

The Firebase verifier and Cashea's merchant API are both faked (the verifier's
own checks are unit-tested in test_host_token.py); what's under test is the
exchange: a verified host identity, enriched with its merchant record when it
has one, becomes a session token that get_principal accepts — and every
failure maps to the right status without leaking why.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from service.api.v1.auth import get_host_verifier, get_merchant_api
from service.core import session_token
from service.core.config import Settings, get_settings
from service.core.host_token import HostIdentity, InvalidHostToken
from service.main import create_app

_KEY = "test-signing-key-with-enough-entropy-0123456789"
_GOOD = "good-host-token"
_EMPLOYEE = {
    "id": 9,
    "role": "ADMIN",
    "merchantId": 42,
    "merchant": {"id": 42, "name": "Tienda Bella"},
    "store": {"id": 7, "uuid": "store-uuid-7", "name": "Sucursal Centro"},
}


class _FakeVerifier:
    def verify(self, token: str) -> HostIdentity:
        if token != _GOOD:
            raise InvalidHostToken("bad")
        return HostIdentity(uid="firebase-uid-1", email="aliado@example.com")


def _merchant_api(status: int, body: object = None) -> httpx.AsyncClient:
    """A merchant API that answers /employees/firebase-uid-1, and only when
    asked with the aliado's own token."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/employees/firebase-uid-1"
        assert request.headers["Authorization"] == f"Bearer {_GOOD}"
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://merchant-api"
    )


def _settings(**overrides: str) -> Callable[[], Settings]:
    values = {
        "ENVIRONMENT": "dev",
        "FIREBASE_PROJECT_ID": "cashea-web-app-stg",
        "SESSION_SIGNING_KEY": _KEY,
        **overrides,
    }
    return lambda: Settings(**values)


def _client(
    settings: Callable[[], Settings],
    merchant_api: httpx.AsyncClient | None = None,
) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_settings] = settings
    app.dependency_overrides[get_host_verifier] = _FakeVerifier
    app.dependency_overrides[get_merchant_api] = lambda: merchant_api
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    async with _client(_settings(), _merchant_api(200, _EMPLOYEE)) as c:
        yield c


async def test_an_aliado_gets_a_session_carrying_their_merchant_record(
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
    assert principal.merchant_name == "Tienda Bella"
    assert principal.store_id == "7"
    assert principal.store_uuid == "store-uuid-7"
    assert principal.store_name == "Sucursal Centro"
    assert principal.role == "ADMIN"


@pytest.mark.parametrize(
    "merchant_api",
    [
        _merchant_api(404, {"message": "not found"}),
        _merchant_api(500, {"message": "boom"}),
        _merchant_api(200, {"id": 9, "role": "ADMIN"}),
        None,
    ],
    ids=["not-an-employee", "backend-error", "no-merchant-id", "lookup-disabled"],
)
async def test_without_a_merchant_record_the_session_is_a_consumers(
    merchant_api: httpx.AsyncClient | None,
) -> None:
    # Never blocks sign-in, never guesses a merchant.
    async with _client(_settings(), merchant_api) as c:
        resp = await c.post("/v1/auth/session", json={"host_token": _GOOD})

    assert resp.status_code == 200
    principal = session_token.verify(resp.json()["session_token"], _KEY)
    assert principal.user_id == "firebase-uid-1"
    assert principal.merchant_id is None
    assert principal.store_name is None


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
