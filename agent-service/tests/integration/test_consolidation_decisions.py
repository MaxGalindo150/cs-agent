"""Integration tests for the consolidation decision sites against a real
PostgreSQL, with a scripted LLM and a scripted decider.

The gate marks a worthless log consolidated without ever calling the
summarizer; the per-fact filter writes only what the decider kept, and sees
what is already stored about the same subject.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import anthropic
from anthropic.types import Message

from agent.decide.fake import FakeDecider, noul
from agent.decide.sites import Decisions
from agent.memory.consolidation import ConsolidationResult, consolidate_user_if_due
from agent.memory.db import Database
from agent.memory.repositories import FactRepository, SessionRepository
from integration.helpers import ScriptedClient, response, text_block

_DISTILLED = (
    '{"facts": [{"subject": "plan", "content": "está en el plan Pro"}, '
    '{"subject": "saludo", "content": "dijo hola"}], '
    '"episode": "se resolvió su duda sobre el plan"}'
)


def _client(script: list[Message]) -> anthropic.AsyncAnthropic:
    return cast(anthropic.AsyncAnthropic, ScriptedClient(script))


async def _seed(db: Database, user_id: str, n: int = 6) -> uuid.UUID:
    async with db.session() as session:
        repo = SessionRepository(session)
        chat = await repo.create_session(user_id=user_id)
        for i in range(n):
            await repo.append_message(chat.id, "user", f"mensaje {i}")
            await repo.append_message(chat.id, "assistant", f"respuesta {i}")
    return chat.id


async def test_gate_skips_and_marks_consolidated_without_calling_the_model(
    database: Database,
) -> None:
    await _seed(database, "usr_alice")
    fake = FakeDecider().script({"worth_it": noul(0.05)})
    events: list[dict[str, Any]] = []

    result = await consolidate_user_if_due(
        database,
        _client([]),  # would raise if the summarizer were called
        "fast-model",
        6,
        "usr_alice",
        Decisions(fake),
        lambda k, e: events.append(e),
    )

    assert result == ConsolidationResult(skipped=True)
    async with database.session() as session:
        repo = SessionRepository(session)
        assert await repo.list_unconsolidated_for_user("usr_alice") == []
        assert await FactRepository(session).list_by_subject("plan", "usr_alice") == []
    assert events[0]["site"] == "consolidation_gate" and events[0]["acted"] is True


async def test_fact_filter_writes_only_kept_facts_and_sees_existing_ones(
    database: Database,
) -> None:
    await _seed(database, "usr_alice")
    async with database.session() as session:
        await FactRepository(session).add(
            "plan", "estaba en el plan Basic", source="user", user_id="usr_alice"
        )
    fake = (
        FakeDecider()
        .script({"worth_it": noul(0.9)})
        .script({"fact_0": noul(0.9), "fact_1": noul(0.1)})
    )

    result = await consolidate_user_if_due(
        database,
        _client([response([text_block(_DISTILLED)])]),
        "fast-model",
        6,
        "usr_alice",
        Decisions(fake),
    )

    assert result == ConsolidationResult(facts=1, episodes=1, dropped_facts=1)
    async with database.session() as session:
        repo = FactRepository(session)
        plan = await repo.list_by_subject("plan", "usr_alice")
        assert sorted(f.content for f in plan) == [
            "estaba en el plan Basic",
            "está en el plan Pro",
        ]
        assert await repo.list_by_subject("saludo", "usr_alice") == []
    state, _ = fake.calls[1]
    assert isinstance(state, dict)
    assert state["already_stored"] == ["[plan] estaba en el plan Basic"]


async def test_failed_decider_consolidates_as_before(database: Database) -> None:
    await _seed(database, "usr_alice")
    fake = FakeDecider().fail(503).fail(503)

    result = await consolidate_user_if_due(
        database,
        _client([response([text_block(_DISTILLED)])]),
        "fast-model",
        6,
        "usr_alice",
        Decisions(fake),
    )

    assert result == ConsolidationResult(facts=2, episodes=1)
