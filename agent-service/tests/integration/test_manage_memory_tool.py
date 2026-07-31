"""Integration tests for the manage_memory tool against a real PostgreSQL.

Ported from waku-agent's manage_memory (search/update/delete only — no
create; episodes are historical, not updatable). Every call is scoped to one
owner (docs/SECURITY.md §3) — the cross-user cases are the point of this
tool existing at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from agent.identity import Principal
from agent.memory.db import Database
from agent.memory.repositories import EpisodeRepository, FactRepository
from agent.tools.context import ToolContext
from agent.tools.implementations.memory import make_manage_memory_tool
from agent.tools.registry import Tool

_ALICE = ToolContext(principal=Principal(user_id="usr_alice"))
_BOB = ToolContext(principal=Principal(user_id="usr_bob"))


def _tool(db: Database) -> Tool:
    return make_manage_memory_tool(db)


def test_tool_requires_identity_and_exposes_no_create_action(
    database: Database,
) -> None:
    tool = _tool(database)
    assert tool.requires_identity is True
    assert tool.input_schema["properties"]["action"]["enum"] == [
        "search",
        "update",
        "delete",
    ]


async def test_search_finds_only_the_callers_own_facts(database: Database) -> None:
    async with database.session() as session:
        await FactRepository(session).add(
            "plan", "está en el plan Pro", user_id="usr_alice"
        )
        await FactRepository(session).add(
            "plan", "está en el plan Pro", user_id="usr_bob"
        )

    out = await _tool(database).fn(_ALICE, action="search", query="plan pro")

    assert "[plan] está en el plan Pro" in out
    assert out.count("[plan]") == 1  # Bob's identical fact never appears


async def test_search_with_no_matching_facts_says_so(database: Database) -> None:
    out = await _tool(database).fn(_ALICE, action="search", query="algo raro")

    assert out == "no matching facts"


async def test_search_episodes_falls_back_to_recent_without_a_query(
    database: Database,
) -> None:
    async with database.session() as session:
        await EpisodeRepository(session).add(
            datetime(2026, 5, 1, tzinfo=UTC), "vieja", user_id="usr_alice"
        )
        await EpisodeRepository(session).add(
            datetime(2026, 7, 1, tzinfo=UTC), "reciente", user_id="usr_alice"
        )

    out = await _tool(database).fn(_ALICE, action="search", kind="episode")

    assert out.splitlines()[0].endswith("reciente")


async def test_search_episodes_with_none_says_so(database: Database) -> None:
    out = await _tool(database).fn(_ALICE, action="search", kind="episode")

    assert out == "no episodes"


async def test_update_corrects_the_callers_own_fact(database: Database) -> None:
    async with database.session() as session:
        fact = await FactRepository(session).add(
            "plan", "está en el plan Pro", user_id="usr_alice"
        )
        fact_id = fact.id

    out = await _tool(database).fn(
        _ALICE, action="update", id=str(fact_id), content="está en el plan Elite"
    )

    assert out == f"Updated fact #{fact_id}."
    async with database.session() as session:
        [reloaded] = await FactRepository(session).list_by_subject(
            "plan", user_id="usr_alice"
        )
        assert reloaded.content == "está en el plan Elite"


async def test_update_cannot_reach_another_users_fact(database: Database) -> None:
    """The whole point of this tool: an id Bob doesn't own is invisible to
    him, not just refused with a different message."""
    async with database.session() as session:
        fact = await FactRepository(session).add(
            "plan", "está en el plan Pro", user_id="usr_alice"
        )
        fact_id = fact.id

    out = await _tool(database).fn(
        _BOB, action="update", id=str(fact_id), content="hackeado"
    )

    assert out == f"No fact with id {fact_id}."
    async with database.session() as session:
        [reloaded] = await FactRepository(session).list_by_subject(
            "plan", user_id="usr_alice"
        )
        assert reloaded.content == "está en el plan Pro"  # untouched


async def test_update_refuses_episodes(database: Database) -> None:
    async with database.session() as session:
        episode = await EpisodeRepository(session).add(
            datetime(2026, 5, 1, tzinfo=UTC), "algo pasó", user_id="usr_alice"
        )
        episode_id = episode.id

    out = await _tool(database).fn(
        _ALICE, action="update", kind="episode", id=str(episode_id), content="x"
    )

    assert out == "Only facts can be updated (episodes are historical)."


async def test_delete_removes_the_callers_own_fact(database: Database) -> None:
    async with database.session() as session:
        fact = await FactRepository(session).add(
            "vpn", "usa split tunnel", user_id="usr_alice"
        )
        fact_id = fact.id

    out = await _tool(database).fn(_ALICE, action="delete", id=str(fact_id))

    assert out == f"Deleted fact #{fact_id}."
    async with database.session() as session:
        assert (
            await FactRepository(session).list_by_subject("vpn", user_id="usr_alice")
            == []
        )


async def test_delete_cannot_reach_another_users_fact(database: Database) -> None:
    async with database.session() as session:
        fact = await FactRepository(session).add(
            "vpn", "usa split tunnel", user_id="usr_alice"
        )
        fact_id = fact.id

    out = await _tool(database).fn(_BOB, action="delete", id=str(fact_id))

    assert out == f"No fact with id {fact_id}."
    async with database.session() as session:
        assert (
            len(
                await FactRepository(session).list_by_subject(
                    "vpn", user_id="usr_alice"
                )
            )
            == 1
        )


async def test_delete_episode_removes_the_callers_own(database: Database) -> None:
    async with database.session() as session:
        episode = await EpisodeRepository(session).add(
            datetime(2026, 5, 1, tzinfo=UTC), "se resolvió", user_id="usr_alice"
        )
        episode_id = episode.id

    out = await _tool(database).fn(
        _ALICE, action="delete", kind="episode", id=str(episode_id)
    )

    assert out == f"Deleted episode #{episode_id}."


async def test_unknown_id_shape_is_a_helpful_message_not_a_crash(
    database: Database,
) -> None:
    out = await _tool(database).fn(
        _ALICE, action="update", id="not-a-uuid", content="x"
    )

    assert "not a valid memory id" in out


async def test_missing_id_on_delete_is_a_helpful_message(database: Database) -> None:
    out = await _tool(database).fn(_ALICE, action="delete", id="")

    assert "not a valid memory id" in out


async def test_unknown_action_is_a_helpful_message(database: Database) -> None:
    out = await _tool(database).fn(_ALICE, action="create", content="x")

    assert out == "action must be one of: search, update, delete"


async def test_random_fact_id_that_exists_for_nobody_reports_not_found(
    database: Database,
) -> None:
    out = await _tool(database).fn(_ALICE, action="delete", id=str(uuid.uuid4()))

    assert "No fact with id" in out
