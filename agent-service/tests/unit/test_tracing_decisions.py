"""Unit tests for the decision and score trace records (Level 1 — no LLM, no DB).

A ``decision`` lands in the trace stream *and* in ``decisions.jsonl``; a
``score`` in the stream and ``scores.jsonl``, with its session id even when
written outside a turn (feedback arrives in a later request).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.ops.tracing import Tracer, TracerConfig


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _trace(trace_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(trace_dir.glob("*.jsonl")):
        if f.name in {"usage.jsonl", "decisions.jsonl", "scores.jsonl"}:
            continue
        out += _lines(f)
    return out


def test_decision_inside_a_turn_is_stamped_and_ledgered(tmp_path: Path) -> None:
    tracer = Tracer(TracerConfig(model="m", trace_dir=tmp_path))
    with tracer.turn("hola", session_id="s1"):
        tracer.event(
            "decision",
            {
                "site": "skill_match",
                "source": "jev",
                "answers": {"skill": {"type": "choice", "choice": "x"}},
                "verdict": {"skills": ["x"]},
                "acted": True,
            },
        )

    ledger = _lines(tmp_path / "decisions.jsonl")
    assert len(ledger) == 1
    assert ledger[0]["session_id"] == "s1"
    assert ledger[0]["site"] == "skill_match"
    assert ledger[0]["answers"]["skill"]["choice"] == "x"
    assert "ts" in ledger[0]
    stream = [r for r in _trace(tmp_path) if r["type"] == "decision"]
    assert stream[0]["turn_id"] == ledger[0]["turn_id"]


def test_score_outside_a_turn_keeps_its_session_and_message(tmp_path: Path) -> None:
    tracer = Tracer(TracerConfig(model="m", trace_dir=tmp_path))

    tracer.score(
        "user_feedback",
        -1,
        message_id="msg_1",
        session_id="s9",
        source="user",
        comment="no era eso",
    )
    tracer.score("jev.diagnosis", "tool_choice", message_id="msg_1", source="jev")
    tracer.score("jev.grounded", True, message_id="msg_1", source="jev")

    ledger = _lines(tmp_path / "scores.jsonl")
    assert [r["name"] for r in ledger] == [
        "user_feedback",
        "jev.diagnosis",
        "jev.grounded",
    ]
    assert ledger[0]["session_id"] == "s9"
    assert ledger[0]["turn_id"] is None
    assert ledger[0]["data_type"] == "NUMERIC"
    assert ledger[1]["data_type"] == "CATEGORICAL"
    assert ledger[2]["data_type"] == "BOOLEAN"
    stream = [r for r in _trace(tmp_path) if r["type"] == "score"]
    assert stream[0]["session_id"] == "s9" and stream[0]["message_id"] == "msg_1"


def test_score_event_through_the_observer_is_ledgered_too(tmp_path: Path) -> None:
    tracer = Tracer(TracerConfig(model="m", trace_dir=tmp_path))
    with tracer.turn("hola", session_id="s1"):
        tracer.event(
            "score",
            {
                "name": "jev.quality",
                "value": 3.0,
                "data_type": "NUMERIC",
                "source": "jev",
                "message_id": "msg_1",
                "comment": None,
            },
        )
    ledger = _lines(tmp_path / "scores.jsonl")
    assert ledger[0]["session_id"] == "s1" and ledger[0]["value"] == 3.0


def test_no_trace_dir_means_no_ledgers_and_no_crash() -> None:
    tracer = Tracer(TracerConfig(model="m", trace_dir=None))
    tracer.event("decision", {"site": "judge", "acted": False})
    tracer.score("x", 1, message_id=None, source="t")
