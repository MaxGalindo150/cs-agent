"""Contract tests for the aliado's host credential on chat calls
(service/core/host_credential.py).

It reaches the agent only for a verified aliado whose X-Host-Token belongs to
the same user as their session token; a bad or mismatched one is a 401; for
anyone else it's ignored. The Firebase verifier and the agent are faked.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from agent.identity import Principal
from agent.loop.agent import LoopResult
from agent.tools.context import ToolContext
from service.core import session_token
from service.core.agent import get_agent
from service.core.config import Settings, get_settings
from service.core.host_token import HostIdentity, InvalidHostToken
from service.main import create_app

_KEY = "test-signing-key-with-enough-entropy-0123456789"
_ALIADO = Principal(user_id="uid-aliado", merchant_id="42", store_name="Centro")
_CUSTOMER = Principal(user_id="uid-customer")
# host token value -> the uid it verifies as
_HOST_TOKENS = {"aliado-token": "uid-aliado", "someone-elses-token": "uid-other"}


class _FakeVerifier:
    def verify(self, token: str) -> HostIdentity:
        if token not in _HOST_TOKENS:
            raise InvalidHostToken("bad")
        return HostIdentity(uid=_HOST_TOKENS[token], email=None)


class _RecordingAgent:
    def __init__(self) -> None:
        self.host_credential: str | None = "never-called"

    async def start_session(
        self, title: str | None = None, principal: Principal | None = None
    ) -> uuid.UUID:
        return uuid.uuid4()

    async def respond(self, *args: Any, **kwargs: Any) -> LoopResult:
        self.host_credential = kwargs.get("host_credential")
        return LoopResult(reply="ok")


def _settings() -> Callable[[], Settings]:
    return lambda: Settings(ENVIRONMENT="dev", SESSION_SIGNING_KEY=_KEY)


async def _chat(
    principal: Principal | None, host_token: str | None
) -> tuple[httpx.Response, _RecordingAgent]:
    app = create_app()
    agent = _RecordingAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    app.dependency_overrides[get_settings] = _settings()
    app.state.host_verifier = _FakeVerifier()
    headers: dict[str, str] = {}
    if principal is not None:
        token = session_token.issue(principal, _KEY, 60)
        headers["Authorization"] = f"Bearer {token}"
    if host_token is not None:
        headers["X-Host-Token"] = host_token
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/v1/chat", json={"message": "hola"}, headers=headers)
    return resp, agent


async def test_an_aliados_own_token_reaches_the_agent() -> None:
    resp, agent = await _chat(_ALIADO, "aliado-token")

    assert resp.status_code == 200
    assert agent.host_credential == "aliado-token"


@pytest.mark.parametrize(
    "host_token", ["someone-elses-token", "forged"], ids=["other-user", "invalid"]
)
async def test_a_mismatched_or_invalid_token_is_401(host_token: str) -> None:
    resp, agent = await _chat(_ALIADO, host_token)

    assert resp.status_code == 401
    assert agent.host_credential == "never-called"


@pytest.mark.parametrize(
    ("principal", "host_token"),
    [(_ALIADO, None), (_CUSTOMER, "aliado-token"), (None, "aliado-token")],
    ids=["aliado-without-header", "customer", "anonymous"],
)
async def test_otherwise_the_agent_gets_no_credential(
    principal: Principal | None, host_token: str | None
) -> None:
    resp, agent = await _chat(principal, host_token)

    assert resp.status_code == 200
    assert agent.host_credential is None


def test_the_credential_never_shows_in_a_repr() -> None:
    ctx = ToolContext(principal=_ALIADO, host_credential="secret-firebase-token")

    assert "secret-firebase-token" not in repr(ctx)
