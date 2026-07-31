"""Behavioural tests for the semantic / episodic stores against real PostgreSQL.

These prove what a mock cannot: that the Database-held store opens a *short*
session per call (add and search run in separate transactions — search only
sees committed data), that it delegates to the FTS repositories, and that it
formats rows the way gated_retrieve injects them. Deterministic, no LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent.memory.db import Database
from agent.memory.episodic.store import PostgresEpisodeStore
from agent.memory.semantic.store import PostgresFactStore


async def test_fact_store_add_then_search_formats_for_injection(
    database: Database,
) -> None:
    store = PostgresFactStore(database)
    await store.add("plan", "el cliente está en el plan Pro anual", user_id="usr_0001")

    # A fresh call → a fresh session: search only sees the committed add.
    results = await store.search("plan pro", user_id="usr_0001")

    assert results == ["[plan] el cliente está en el plan Pro anual"]


async def test_fact_store_search_returns_empty_on_no_match(
    database: Database,
) -> None:
    store = PostgresFactStore(database)
    await store.add("vpn", "el cliente usa split tunnel", user_id="usr_0001")

    # No shared lexemes → no rows, and no unrelated fallback is injected.
    assert await store.search("facturación mensual", user_id="usr_0001") == []


async def test_fact_store_search_never_crosses_users(database: Database) -> None:
    store = PostgresFactStore(database)
    await store.add("plan", "el cliente está en el plan Pro", user_id="usr_alice")
    await store.add("plan", "el cliente está en el plan Pro", user_id="usr_bob")

    assert await store.search("plan pro", user_id="usr_alice") == [
        "[plan] el cliente está en el plan Pro"
    ]


async def test_episode_store_add_then_search_formats_with_date(
    database: Database,
) -> None:
    store = PostgresEpisodeStore(database)
    happened_at = datetime(2026, 7, 1, tzinfo=UTC)
    await store.add("se resolvió el timeout de la vpn", happened_at, user_id="usr_0001")

    results = await store.search("vpn timeout", user_id="usr_0001")

    assert results == ["(2026-07-01) se resolvió el timeout de la vpn"]


async def test_episode_store_search_without_usable_terms_falls_back_to_recency(
    database: Database,
) -> None:
    """Waku's behaviour: a query with nothing to search on returns recent
    episodes rather than nothing."""
    store = PostgresEpisodeStore(database)
    await store.add(
        "lo más viejo", datetime(2026, 1, 1, tzinfo=UTC), user_id="usr_0001"
    )
    await store.add(
        "lo más reciente", datetime(2026, 7, 1, tzinfo=UTC), user_id="usr_0001"
    )

    assert await store.search("!!! ???", user_id="usr_0001", top_k=1) == [
        "(2026-07-01) lo más reciente"
    ]
