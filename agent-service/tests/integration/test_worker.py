"""Integration test for POST /internal/consolidate against a real PostgreSQL
and a scripted LLM — the success path end to end (auth gate itself is covered
by tests/contract/test_worker.py).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import anthropic
import httpx
import pytest
from anthropic.types import Message

from agent.memory.db import Database
from agent.memory.repositories import FactRepository, SessionRepository
from integration.helpers import ScriptedClient, response, text_block
from service.core.agent import get_database
from service.core.config import Settings, get_settings
from service.core.llm import get_llm_client
from service.main import create_app

_TOKEN = "test-worker-secret"
_DISTILLED = (
    '{"facts": [{"subject": "plan", "content": "está en el plan Pro"}], '
    '"episode": "se resolvió su duda sobre el plan"}'
)


def _client(script: list[Message]) -> anthropic.AsyncAnthropic:
    return cast(anthropic.AsyncAnthropic, ScriptedClient(script))


@pytest.fixture
async def worker_api(database: Database) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        INTERNAL_WORKER_TOKEN=_TOKEN
    )
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_llm_client] = lambda: _client(
        [response([text_block(_DISTILLED)])]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_consolidate_endpoint_sweeps_due_users(
    worker_api: httpx.AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        repo = SessionRepository(session)
        chat = await repo.create_session(user_id="usr_alice")
        for i in range(6):
            await repo.append_message(chat.id, "user", f"mensaje {i}")
            await repo.append_message(chat.id, "assistant", f"respuesta {i}")

    resp = await worker_api.post(
        "/internal/consolidate", headers={"X-Worker-Token": _TOKEN}
    )

    assert resp.status_code == 200
    assert resp.json() == {"usr_alice": {"facts": 1, "episodes": 1}}
    async with database.session() as session:
        facts = await FactRepository(session).list_by_subject(
            "plan", user_id="usr_alice"
        )
        assert [f.content for f in facts] == ["está en el plan Pro"]


async def test_consolidate_endpoint_with_nothing_due_touches_no_llm(
    worker_api: httpx.AsyncClient,
) -> None:
    resp = await worker_api.post(
        "/internal/consolidate", headers={"X-Worker-Token": _TOKEN}
    )

    assert resp.status_code == 200
    assert resp.json() == {}
