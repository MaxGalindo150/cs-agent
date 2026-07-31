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
from agent.runtime.session import Session


async def test_system_prompt_includes_a_clock_with_hh_mm() -> None:
    # Regression net from Waku: the model had the date but not the time and asked
    # the user "what time is it?" before scheduling "in 30 minutes". The system
    # prompt must carry a real HH:MM clock so it never has to ask.
    session = Session(uuid.uuid4(), memory=None)
    system = await session.build_system("qué hago en 30 min?")
    assert "Right now it is" in system
    assert re.search(r"\b\d{2}:\d{2}\b", system), "system prompt missing an HH:MM clock"


async def test_build_system_without_memory_is_soul_plus_clock_only() -> None:
    # With no memory wired, working memory degrades to SOUL + clock: no retrieval,
    # no skills sections (Memory is optional by construction).
    system = await Session(uuid.uuid4(), memory=None).build_system("hola")
    assert "Cheo" in system  # the SOUL persona is present
    assert "Relevant memory" not in system
    assert "Relevant skill instructions" not in system


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
