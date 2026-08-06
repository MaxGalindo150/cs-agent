"""Unit tests for working-memory assembly (Level 1 — deterministic, no LLM, no DB).

Ported from Waku's ``test_working_memory`` / ``test_history_window`` — the
portable, DB-free subset. Adapted to our first-class UUID sessions and the
history-window knob that now lives on ``AgentConfig`` (Waku read it from settings).

The DB- and LLM-backed parts of those Waku tests (windowing end to end, meta
persistence) become integration tests once the ``respond()`` harness lands — see
``tests/integration/README.md``.
"""

from __future__ import annotations

import re
import uuid

from agent.app import AgentConfig
from agent.identity import Principal
from agent.runtime.session import Session


class _StubMemory:
    """Just enough of the ``Memory`` facade for ``fixed_response`` — it only
    ever calls ``is_escalated``."""

    def __init__(self, escalated: bool) -> None:
        self._escalated = escalated

    async def is_escalated(self, session_id: uuid.UUID) -> bool:
        return self._escalated


async def test_system_prompt_includes_a_clock_with_hh_mm() -> None:
    # Regression net from Waku: the model had the date but not the time and asked
    # the user "what time is it?" before scheduling "in 30 minutes". The system
    # prompt must carry a real HH:MM clock so it never has to ask.
    session = Session(uuid.uuid4(), memory=None)
    system = await session.build_system("qué hago en 30 min?")
    assert "Right now it is" in system
    assert re.search(r"\b\d{2}:\d{2}\b", system), "system prompt missing an HH:MM clock"


async def test_build_system_without_memory_omits_memory_sections() -> None:
    # With no memory wired, working memory keeps only static/runtime context: no
    # retrieval or skills sections (Memory is optional by construction).
    system = await Session(uuid.uuid4(), memory=None).build_system("hola")
    assert "Cheo" in system  # the SOUL persona is present
    assert "No caller is identified" in system
    assert "Relevant memory" not in system
    assert "Relevant skill instructions" not in system


async def test_build_system_tells_merchant_agent_identity_is_already_scoped() -> None:
    principal = Principal(
        user_id="merchant:1",
        profile="merchant",
        merchant_id="1",
    )

    system = await Session(uuid.uuid4(), memory=None).build_system(
        "¿Cuántas órdenes tengo?", principal=principal
    )

    assert "A merchant is already identified" in system
    assert "Do not ask for their RIF" in system
    assert "merchant:1" not in system
    assert "merchant_id=1" not in system


def test_fresh_session_carries_its_id() -> None:
    sid = uuid.uuid4()
    assert Session(sid, memory=None).session_id == sid


def test_start_new_switches_id_and_clears_working_memory() -> None:
    session = Session(uuid.uuid4(), memory=None)
    session.history.append({"role": "user", "content": "old turn"})

    new_id = uuid.uuid4()
    session.start_new(new_id)

    assert session.session_id == new_id
    assert session.history == []


def test_default_history_window_is_generous_but_finite() -> None:
    # Waku's regression: the working-memory window must stay bounded — an
    # unbounded history re-sends the whole thread every turn (cost/latency climb,
    # eventual context-limit break). The knob now lives on AgentConfig, injected
    # into Session.switch, defaulting to 12 turns.
    assert AgentConfig(model="test-model").history_turns == 12


async def test_fixed_response_is_none_without_memory() -> None:
    session = Session(uuid.uuid4(), memory=None)
    assert await session.fixed_response("hola") is None


async def test_fixed_response_is_none_when_not_escalated() -> None:
    session = Session(uuid.uuid4(), memory=_StubMemory(escalated=False))
    assert await session.fixed_response("hola") is None


async def test_fixed_response_short_circuits_an_escalated_session() -> None:
    """The deterministic gate: an escalated session gets a canned reply, no
    matter what the user says — never a fresh model-generated promise."""
    session = Session(uuid.uuid4(), memory=_StubMemory(escalated=True))

    fixed = await session.fixed_response("¿ya me van a reembolsar?")

    assert fixed is not None
    assert "human agent" in fixed.lower()
