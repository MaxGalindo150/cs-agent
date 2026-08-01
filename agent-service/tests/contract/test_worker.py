"""Contract tests for POST /internal/consolidate — the worker trigger's HTTP
auth gate (Level 1 — no real DB/LLM touched; the endpoint's exception chain
guarantees the handler body, and therefore the db/client dependencies, never
runs when the token check fails). Consolidation logic itself is covered by
tests/integration/test_consolidation.py; the success path end-to-end is
covered by tests/integration/test_worker.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from service.core.agent import get_database
from service.core.config import Settings, get_settings
from service.core.llm import get_llm_client
from service.main import create_app

_TOKEN = "test-worker-secret"


def _settings(token: str) -> Settings:
    return Settings(INTERNAL_WORKER_TOKEN=token)


@pytest.fixture
async def worker_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(_TOKEN)
    # A failed token check aborts the dependency chain before the handler body
    # runs (FastAPI/Starlette guarantee) — db/client are never touched, so a
    # bare None placeholder is safe here.
    app.dependency_overrides[get_database] = lambda: None
    app.dependency_overrides[get_llm_client] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_missing_token_is_refused(worker_client: httpx.AsyncClient) -> None:
    resp = await worker_client.post("/internal/consolidate")

    assert resp.status_code == 401


async def test_wrong_token_is_refused(worker_client: httpx.AsyncClient) -> None:
    resp = await worker_client.post(
        "/internal/consolidate", headers={"X-Worker-Token": "not-the-secret"}
    )

    assert resp.status_code == 401


async def test_unconfigured_token_refuses_every_request() -> None:
    """Fail-closed: an empty INTERNAL_WORKER_TOKEN (its default) must never
    match anything a caller sends, including an empty header."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings("")
    app.dependency_overrides[get_database] = lambda: None
    app.dependency_overrides[get_llm_client] = lambda: None
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/internal/consolidate", headers={"X-Worker-Token": ""})

    assert resp.status_code == 401
