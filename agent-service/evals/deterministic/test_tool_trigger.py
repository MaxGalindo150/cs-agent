"""LIVE TOOL-SELECTION EVAL — "did the agent pick the right tool?"

The scripted-client version of this question (does the harness invoke the
tool a *given* model response asks for) is already covered deterministically
by ``tests/unit/test_loop.py`` / ``tests/integration/test_respond.py`` — this
is NOT that. This calls the REAL model and checks its own choice against
``evals/dataset.jsonl`` with a plain, judge-free assert (CLAUDE.md §8 Level 2
"tool-selection eval ... the Cheo lesson").

The dataset's core case, and the reason this eval exists: anything the tool
registry has NO tool for must escalate — never a hallucinated "I'll take
care of it". ``escalate_to_human`` needs no identity, so those cases run
anonymous; a couple of "covered" cases (which DO need identity) are a
negative control — an agent that escalates everything would trivially pass
the cases above, so this also checks it does its job when it can.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.identity import Principal
from agent.memory.db import Database
from evals.helpers import HAS_KEY, make_agent_live, resolve_demo_user

_DATASET_PATH = Path(__file__).resolve().parents[1] / "dataset.jsonl"
DATASET = [
    json.loads(line) for line in _DATASET_PATH.read_text().splitlines() if line.strip()
]


@pytest.mark.skipif(not HAS_KEY, reason="live eval needs a real ANTHROPIC_API_KEY")
@pytest.mark.parametrize("case", DATASET, ids=[c["id"] for c in DATASET])
async def test_dataset_case(case: dict[str, Any], database: Database) -> None:
    agent = make_agent_live(database)
    principal = None
    if "principal_scenario" in case:
        principal = Principal(user_id=resolve_demo_user(case["principal_scenario"]))

    session_id = await agent.start_session("eval", principal=principal)
    result = await agent.respond(session_id, case["input"], principal=principal)
    fired = [c["tool"] for c in result.tool_calls]

    if case["expect_tool"] is None:
        assert fired == [], f"expected no tools, model called {fired}"
        return

    assert case["expect_tool"] in fired, (
        f"expected {case['expect_tool']}, model called {fired or 'nothing'}"
    )
    want = case.get("expect_min_tool_calls", 0)
    assert len(fired) >= want, f"only {len(fired)} tool calls, wanted >= {want}"
