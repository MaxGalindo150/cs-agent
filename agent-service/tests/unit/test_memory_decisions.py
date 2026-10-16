"""Unit tests for the memory facade's decision sites (Level 1 — no DB, no LLM).

With a decider: the Haiku gate is never called, both stores are searched on
a retrieve, the retrieved rows are re-ranked, and the skill match is a choice
over descriptions with the keyword matcher as fallback. Without one, or on a
failed call, the facade behaves as it always did.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import anthropic
import pytest
from anthropic.types import Message, TextBlock, Usage

import agent.memory as memory_module
from agent.decide.fake import FakeDecider, choice, noul
from agent.decide.sites import Decisions
from agent.memory import Memory, MemoryConfig
from agent.memory.db import Database
from agent.runtime.session import Session


def _msg(text: str) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=[TextBlock(type="text", text=text, citations=None)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


class _CountingMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def create(self, **kwargs: Any) -> Message:
        self.calls += 1
        return _msg(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = _CountingMessages(text)


class _FakeStore:
    def __init__(self, results: list[str]) -> None:
        self._results = results
        self.queries: list[str] = []

    async def search(
        self, query: str, user_id: str | None, top_k: int = 4
    ) -> list[str]:
        self.queries.append(query)
        return list(self._results)


def _memory(
    decider: FakeDecider | None,
    facts: _FakeStore,
    episodes: _FakeStore,
    monkeypatch: pytest.MonkeyPatch,
    haiku_says: str = '{"retrieve": true, "query": "haiku", "reason": "h"}',
) -> tuple[Memory, _FakeClient]:
    client = _FakeClient(haiku_says)
    mem = Memory(
        cast(Database, object()),
        cast(anthropic.AsyncAnthropic, client),
        MemoryConfig(fast_model="fast"),
        decisions=Decisions(decider),
    )
    monkeypatch.setattr(mem, "facts", facts)
    monkeypatch.setattr(mem, "episodes", episodes)
    return mem, client


async def test_jev_gate_replaces_the_haiku_call_and_searches_both_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts, episodes = _FakeStore(["[plan] pro"]), _FakeStore(["(ayer) timeout"])
    fake = (
        FakeDecider()
        .script({"needs_history": noul(0.9), "memory_kind": choice("episodes", 0.95)})
        .script({"row_0": noul(0.2), "row_1": noul(0.8)})
    )
    mem, client = _memory(fake, facts, episodes, monkeypatch)
    events: list[tuple[str, dict[str, Any]]] = []

    out = await mem.gated_retrieve(
        "sigue el timeout", "usr_1", notify=lambda k, e: events.append((k, e))
    )

    assert client.messages.calls == 0  # no Haiku round-trip
    # A confident kind is recorded, never acted on: both stores run, and the
    # per-row re-rank is what keeps the prompt clean.
    assert facts.queries == ["sigue el timeout"]
    assert episodes.queries == ["sigue el timeout"]
    assert out == "(ayer) timeout"
    gate = [e for k, e in events if k == "gate"]
    assert gate == [{"decision": "retrieve", "reason": "jev p=0.90"}]
    assert [e["site"] for k, e in events if k == "decision"] == [
        "retrieval",
        "memory_select",
    ]


async def test_rerank_drops_rows_the_decider_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _FakeStore(["[a] keep", "[b] drop"])
    fake = (
        FakeDecider()
        .script({"needs_history": noul(0.9), "memory_kind": choice("facts", 0.95)})
        .script({"row_0": noul(0.9), "row_1": noul(0.1)})
    )
    mem, _ = _memory(fake, facts, _FakeStore([]), monkeypatch)

    assert await mem.gated_retrieve("m", "usr_1") == "[a] keep"


async def test_jev_skip_touches_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    facts = _FakeStore(["never"])
    fake = FakeDecider().script(
        {"needs_history": noul(0.1), "memory_kind": choice("facts", 0.95)}
    )
    mem, _ = _memory(fake, facts, _FakeStore([]), monkeypatch)
    assert await mem.gated_retrieve("gracias", "usr_1") == ""
    assert facts.queries == []


async def test_failed_decider_falls_back_to_the_haiku_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _FakeStore(["[x] y"])
    mem, client = _memory(FakeDecider().fail(503), facts, _FakeStore([]), monkeypatch)

    out = await mem.gated_retrieve("m", "usr_1")

    assert client.messages.calls == 1
    assert facts.queries == ["haiku"]  # the Haiku gate's distilled query
    assert out == "[x] y"


async def test_no_decider_is_the_previous_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _FakeStore(["[x] y"])
    mem, client = _memory(None, facts, _FakeStore([]), monkeypatch)
    out = await mem.gated_retrieve("m", "usr_1")
    assert client.messages.calls == 1 and out == "[x] y"


# ---- skills -----------------------------------------------------------------------


def _skills_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    for name, desc in (
        ("daily-closing", "Usar cuando el aliado pregunta por el cierre de caja."),
        ("create-order", "Usar cuando el aliado pregunta cómo crear una orden."),
    ):
        d = root / "merchant" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\nbody of {name}\n"
        )
    return root


async def test_skill_match_is_a_choice_over_descriptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(memory_module, "REPO_SKILLS", _skills_dir(tmp_path))
    fake = FakeDecider().script({"skill": choice("daily-closing", 0.97)})
    mem, _ = _memory(fake, _FakeStore([]), _FakeStore([]), monkeypatch)
    events: list[dict[str, Any]] = []

    # keywords alone would not match: "cerrar" ≠ "cierre", one overlap only
    text = await mem.matching_skills(
        "cómo cerrar la caja hoy", "merchant", lambda k, e: events.append(e)
    )

    assert "body of daily-closing" in text and "create-order" not in text
    state, questions = fake.calls[0]
    assert state == "cómo cerrar la caja hoy"
    assert set(questions["skill"]["criteria"]) == {
        "daily-closing",
        "create-order",
        "none",
    }
    assert events[0]["baseline"] == {"skills": []}
    assert events[0]["agreement"] is False


async def test_unsure_skill_match_keeps_the_keyword_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(memory_module, "REPO_SKILLS", _skills_dir(tmp_path))
    fake = FakeDecider().script({"skill": choice("daily-closing", 0.6)})
    mem, _ = _memory(fake, _FakeStore([]), _FakeStore([]), monkeypatch)

    # "crear" + "orden" overlap the create-order description → keyword pick
    picked = await mem.select_skills("quiero crear una orden", "merchant")

    assert [s.name for s in picked] == ["create-order"]


async def test_skill_catalog_lists_names_and_descriptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(memory_module, "REPO_SKILLS", _skills_dir(tmp_path))
    mem, _ = _memory(None, _FakeStore([]), _FakeStore([]), monkeypatch)
    assert [n for n, _ in mem.skill_catalog("merchant")] == [
        "create-order",
        "daily-closing",
    ]
    assert mem.skill_catalog("consumer") == []


# ---- session records what it loaded ---------------------------------------------


class _StubMemory:
    def __init__(self, skills: list[Any]) -> None:
        self._skills = skills

    async def gated_retrieve(self, *a: Any, **k: Any) -> str:
        return "[plan] pro"

    async def select_skills(self, *a: Any, **k: Any) -> list[Any]:
        return self._skills

    async def is_escalated(self, *a: Any) -> bool:
        return False


async def test_build_system_records_loaded_skills_and_joins_both_sections() -> None:
    import uuid
    from types import SimpleNamespace

    skill = SimpleNamespace(name="daily-closing", body="cierra así")
    session = Session(uuid.uuid4(), memory=_StubMemory([skill]))

    system = await session.build_system("caja")

    assert session.skills_loaded == ["daily-closing"]
    assert "Relevant memory:\n[plan] pro" in system
    assert "### daily-closing\ncierra así" in system
