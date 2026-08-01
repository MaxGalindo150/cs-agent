"""Integration tests for consolidation (agent/memory/consolidation.py) against
a real PostgreSQL, with a scripted (offline) LLM — same harness as
tests/integration/test_respond.py, ported from waku-agent's consolidation.

The summarizer is scripted, not real, so these assert the *orchestration*:
batching threshold, per-user isolation, and "never lose the log on failure" —
not the LLM's actual extraction quality (that's an L2/L3 eval concern,
CLAUDE.md §8).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import anthropic
from anthropic.types import Message

from agent.memory.consolidation import (
    ConsolidationResult,
    consolidate_all_due_users,
    consolidate_user_if_due,
)
from agent.memory.db import Database
from agent.memory.repositories import (
    EpisodeRepository,
    FactRepository,
    SessionRepository,
)
from integration.helpers import ScriptedClient, response, text_block

_DISTILLED = (
    '{"facts": [{"subject": "plan", "content": "está en el plan Pro"}], '
    '"episode": "se resolvió su duda sobre el plan"}'
)


def _client(script: list[Message]) -> anthropic.AsyncAnthropic:
    return cast(anthropic.AsyncAnthropic, ScriptedClient(script))


class _TrackingMessages:
    """Records how many ``create`` calls were in flight at once — proves the
    semaphore in ``consolidate_all_due_users`` actually bounds concurrency,
    something a canned ``ScriptedClient`` script can't observe."""

    def __init__(self, outer: _ConcurrencyTrackingClient) -> None:
        self._outer = outer

    async def create(self, **kwargs: Any) -> Message:
        self._outer.in_flight += 1
        self._outer.max_in_flight = max(
            self._outer.max_in_flight, self._outer.in_flight
        )
        await asyncio.sleep(0.01)  # let concurrent calls overlap
        self._outer.in_flight -= 1
        return response([text_block(_DISTILLED)])


class _ConcurrencyTrackingClient:
    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0
        self.messages = _TrackingMessages(self)


async def _new_session(db: Database, user_id: str | None = None) -> uuid.UUID:
    async with db.session() as session:
        chat = await SessionRepository(session).create_session(user_id=user_id)
    return chat.id


async def _seed_exchanges(db: Database, chat_id: uuid.UUID, n: int) -> None:
    """n user/assistant exchanges (2n messages), unconsolidated, in one session."""
    async with db.session() as session:
        repo = SessionRepository(session)
        for i in range(n):
            await repo.append_message(chat_id, "user", f"mensaje {i}")
            await repo.append_message(chat_id, "assistant", f"respuesta {i}")


async def test_below_threshold_does_nothing_and_never_calls_the_model(
    database: Database,
) -> None:
    chat = await _new_session(database, user_id="usr_alice")
    await _seed_exchanges(database, chat, n=2)  # every_n=6 needs 6
    client = _client([])  # would raise "ran out of scripted responses"

    result = await consolidate_user_if_due(
        database, client, "fast-model", 6, "usr_alice"
    )

    assert result == ConsolidationResult()
    async with database.session() as session:
        assert (
            await SessionRepository(session).list_unconsolidated_for_user("usr_alice")
            != []
        )


async def test_at_threshold_writes_facts_episode_and_marks_consolidated(
    database: Database,
) -> None:
    chat = await _new_session(database, user_id="usr_alice")
    await _seed_exchanges(database, chat, n=6)
    client = _client([response([text_block(_DISTILLED)])])

    result = await consolidate_user_if_due(
        database, client, "fast-model", 6, "usr_alice"
    )

    assert result == ConsolidationResult(facts=1, episodes=1)
    async with database.session() as session:
        facts = await FactRepository(session).list_by_subject(
            "plan", user_id="usr_alice"
        )
        assert [f.content for f in facts] == ["está en el plan Pro"]
        assert facts[0].source == "consolidation"

        episodes = await EpisodeRepository(session).list_recent(user_id="usr_alice")
        assert [e.summary for e in episodes] == ["se resolvió su duda sobre el plan"]

        assert (
            await SessionRepository(session).list_unconsolidated_for_user("usr_alice")
            == []
        )


async def test_malformed_response_leaves_the_log_unconsolidated(
    database: Database,
) -> None:
    """Never lose the log: a summarizer failure must not mark anything
    consolidated — the next sweep gets another chance."""
    chat = await _new_session(database, user_id="usr_alice")
    await _seed_exchanges(database, chat, n=6)
    client = _client([response([text_block("not json at all")])])

    result = await consolidate_user_if_due(
        database, client, "fast-model", 6, "usr_alice"
    )

    assert result == ConsolidationResult()
    async with database.session() as session:
        pending = await SessionRepository(session).list_unconsolidated_for_user(
            "usr_alice"
        )
        assert len(pending) == 12  # 6 exchanges * 2 messages, untouched


async def test_malformed_shape_leaves_the_log_unconsolidated(
    database: Database,
) -> None:
    """Valid JSON with the wrong shape (facts not a list, episode not a
    string) must be treated the same as unparseable JSON — one bad response
    fails only this user, not the whole sweep (asyncio.gather would
    otherwise propagate an uncaught AttributeError/TypeError)."""
    chat = await _new_session(database, user_id="usr_alice")
    await _seed_exchanges(database, chat, n=6)
    client = _client([response([text_block('{"facts": "not a list", "episode": 42}')])])

    result = await consolidate_user_if_due(
        database, client, "fast-model", 6, "usr_alice"
    )

    assert result == ConsolidationResult()
    async with database.session() as session:
        pending = await SessionRepository(session).list_unconsolidated_for_user(
            "usr_alice"
        )
        assert len(pending) == 12  # untouched, retried next sweep


async def test_non_string_fact_fields_are_skipped_not_persisted(
    database: Database,
) -> None:
    """A dict-shaped fact with a non-string subject/content (e.g. the LLM
    hallucinates a number) is silently skipped, not written to a repository
    that expects ``str`` — unlike a malformed container shape, a valid
    container with one bad item doesn't fail the whole response."""
    chat = await _new_session(database, user_id="usr_alice")
    await _seed_exchanges(database, chat, n=6)
    client = _client(
        [response([text_block('{"facts": [{"subject": 1, "content": "x"}]}')])]
    )

    result = await consolidate_user_if_due(
        database, client, "fast-model", 6, "usr_alice"
    )

    assert result == ConsolidationResult()
    async with database.session() as session:
        assert await FactRepository(session).search("x", user_id="usr_alice") == []
        # container shape was valid, so the log is still marked consolidated
        assert (
            await SessionRepository(session).list_unconsolidated_for_user("usr_alice")
            == []
        )


async def test_consolidate_all_due_users_sweeps_independently(
    database: Database,
) -> None:
    alice_chat = await _new_session(database, user_id="usr_alice")
    bob_chat = await _new_session(database, user_id="usr_bob")
    await _seed_exchanges(database, alice_chat, n=6)
    await _seed_exchanges(database, bob_chat, n=2)  # below threshold
    client = _client([response([text_block(_DISTILLED)])])  # only alice is due

    results = await consolidate_all_due_users(
        database, client, "fast-model", 6, batch_size=50, max_concurrency=5
    )

    assert results == {
        "usr_alice": ConsolidationResult(facts=1, episodes=1),
        "usr_bob": ConsolidationResult(),
    }


async def test_consolidate_all_due_users_skips_anonymous_sessions(
    database: Database,
) -> None:
    anon_chat = await _new_session(database)  # no user_id
    await _seed_exchanges(database, anon_chat, n=6)
    client = _client([])  # must never be called — no owner to consolidate

    results = await consolidate_all_due_users(
        database, client, "fast-model", 6, batch_size=50, max_concurrency=5
    )

    assert results == {}


async def test_consolidate_all_due_users_bounds_concurrency(
    database: Database,
) -> None:
    for i in range(5):
        chat = await _new_session(database, user_id=f"usr_{i}")
        await _seed_exchanges(database, chat, n=6)
    tracker = _ConcurrencyTrackingClient()
    client = cast(anthropic.AsyncAnthropic, tracker)

    results = await consolidate_all_due_users(
        database, client, "fast-model", 6, batch_size=50, max_concurrency=2
    )

    assert len(results) == 5
    assert tracker.max_in_flight <= 2


async def test_consolidate_all_due_users_respects_batch_size(
    database: Database,
) -> None:
    """A backlog bigger than one sweep's batch leaves the rest for the next
    sweep — the oldest-waiting users go first (repository-level guarantee)."""
    for i in range(5):
        chat = await _new_session(database, user_id=f"usr_{i}")
        await _seed_exchanges(database, chat, n=6)
    client = _client([response([text_block(_DISTILLED)]) for _ in range(2)])

    results = await consolidate_all_due_users(
        database, client, "fast-model", 6, batch_size=2, max_concurrency=5
    )

    assert set(results) == {"usr_0", "usr_1"}
