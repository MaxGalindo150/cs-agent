"""Unit tests for the Memory facade's gated_retrieve (Level 1 — deterministic).

No database and no real LLM: the gate's client is faked, and the semantic /
episodic stores are swapped for fakes. This isolates the *orchestration* — does
the facade honour the gate's verdict, wire the gate's query into the search, and
join facts with episodes — from the storage behaviour (covered against real
Postgres in tests/integration/test_memory_stores.py).
"""

from __future__ import annotations

from typing import Any, cast

import anthropic
import pytest
from anthropic.types import Message, TextBlock, Usage

from agent.memory import Memory, MemoryConfig
from agent.memory.db import Database


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _msg(text: str) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=[_text(text)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


class _FakeMessages:
    def __init__(self, response: Message | Exception) -> None:
        self._response = response

    async def create(self, **kwargs: Any) -> Message:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeClient:
    def __init__(self, response: Message | Exception) -> None:
        self.messages = _FakeMessages(response)


class _FakeStore:
    """Stands in for a Postgres store: records the query, returns canned rows."""

    def __init__(self, results: list[str]) -> None:
        self._results = results
        self.queries: list[str] = []
        self.user_ids: list[str | None] = []

    async def search(
        self, query: str, user_id: str | None, top_k: int = 4
    ) -> list[str]:
        self.queries.append(query)
        self.user_ids.append(user_id)
        return list(self._results)


def _memory(
    gate_response: Message | Exception,
    facts: _FakeStore,
    episodes: _FakeStore,
    monkeypatch: pytest.MonkeyPatch,
    config: MemoryConfig | None = None,
) -> Memory:
    client = cast(anthropic.AsyncAnthropic, _FakeClient(gate_response))
    # The facade only stores the db; PostgresFactStore(db) opens no connection
    # at construction, so a dummy object is safe — the stores are replaced next.
    mem = Memory(
        cast(Database, object()),
        client,
        config or MemoryConfig(fast_model="fast"),
    )
    monkeypatch.setattr(mem, "facts", facts)
    monkeypatch.setattr(mem, "episodes", episodes)
    return mem


async def test_skips_retrieval_and_touches_no_store_when_gate_says_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts, episodes = _FakeStore(["[x] never"]), _FakeStore(["(2026-01-01) never"])
    mem = _memory(
        _msg('{"retrieve": false, "reason": "greeting"}'),
        facts,
        episodes,
        monkeypatch,
    )
    events: list[tuple[str, dict[str, Any]]] = []

    def notify(kind: str, event: dict[str, Any]) -> None:
        events.append((kind, event))

    out = await mem.gated_retrieve("¡gracias!", "usr_0001", notify=notify)

    assert out == ""
    assert facts.queries == []  # the store is never hit on a skip
    assert episodes.queries == []
    assert events == [("gate", {"decision": "skip", "reason": "greeting"})]


async def test_joins_facts_and_episodes_using_the_gates_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _FakeStore(["[vpn] el cliente usa split tunnel"])
    episodes = _FakeStore(["(2026-07-01) se resolvió un timeout de vpn"])
    mem = _memory(
        _msg('{"retrieve": true, "query": "vpn", "reason": "past fix"}'),
        facts,
        episodes,
        monkeypatch,
        config=MemoryConfig(fast_model="fast", retrieval_top_k=2, episode_top_k=1),
    )

    out = await mem.gated_retrieve("sigue fallando la vpn", "usr_0001")

    assert "split tunnel" in out
    assert "timeout de vpn" in out
    # the search runs on the gate's distilled query, not the raw message
    assert facts.queries == ["vpn"]
    assert episodes.queries == ["vpn"]
    # and every search is scoped to the caller — never left unfiltered
    assert facts.user_ids == ["usr_0001"]
    assert episodes.user_ids == ["usr_0001"]


async def test_fail_open_searches_with_the_raw_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _FakeStore(["[plan] plan Pro anual"])
    episodes = _FakeStore([])
    mem = _memory(RuntimeError("gate down"), facts, episodes, monkeypatch)

    out = await mem.gated_retrieve("¿cuál es mi plan?", "usr_0001")

    # gate failed → fail open → retrieve using the message itself as the query
    assert facts.queries == ["¿cuál es mi plan?"]
    assert "plan Pro anual" in out
