"""Unit tests for the Tracer + compose (Level 1 — deterministic, no LLM, no DB).

Waku only tests the trace *reader* (``ops/show_trace``); we don't port that, so
these cover the *writer* directly: what lands in the JSONL sink, what is skipped,
how ``llm`` events are stamped, the turn markers, the usage ledger, and the
stdout-only (no trace dir) and OTel-off defaults.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from agent.observability import LoopEvent, Observer
from agent.ops.tracing import Tracer, TracerConfig, compose


def _cfg(trace_dir: Path | None, **kw: Any) -> TracerConfig:
    return TracerConfig(model=kw.pop("model", "test-model"), trace_dir=trace_dir, **kw)


def _trace_lines(trace_dir: Path) -> list[dict[str, Any]]:
    """All trace records written to the dated JSONL file (excludes usage.jsonl)."""
    records: list[dict[str, Any]] = []
    for f in sorted(trace_dir.glob("*.jsonl")):
        if f.name == "usage.jsonl":
            continue
        records += [json.loads(line) for line in f.read_text().splitlines()]
    return records


def _usage_lines(trace_dir: Path) -> list[dict[str, Any]]:
    path = trace_dir / "usage.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


# ---- the JSONL sink -------------------------------------------------------


def test_event_writes_a_jsonl_record_with_type_and_ts(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path))
    tracer.event("tool", {"tool": "get_order", "args": {}, "output": "ok"})

    records = _trace_lines(tmp_path)
    assert len(records) == 1
    assert records[0]["type"] == "tool"
    assert records[0]["tool"] == "get_order"
    assert "ts" in records[0]


def test_streaming_text_deltas_are_not_traced(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path))
    tracer.event("text", {"delta": "ho"})
    tracer.event("text", {"delta": "la"})

    assert _trace_lines(tmp_path) == []


def test_llm_event_is_stamped_with_provider_and_model(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path, model="claude-x", provider="anthropic"))
    tracer.event("llm", {"iteration": 1, "usage": {"in": 10, "out": 5}})

    record = _trace_lines(tmp_path)[0]
    assert record["type"] == "llm"
    assert record["provider"] == "anthropic"
    assert record["model"] == "claude-x"


# ---- turn markers ---------------------------------------------------------


def test_turn_brackets_write_start_and_end_markers(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path))
    with tracer.turn("hola"):
        tracer.event("gate", {"decision": "skip", "reason": "small talk"})
    tracer.end_turn("hi", iterations=1)

    types = [r["type"] for r in _trace_lines(tmp_path)]
    assert types == ["turn_start", "gate", "turn_end"]


# ---- session binding ------------------------------------------------------


def test_every_record_in_a_turn_carries_the_session_id(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path))
    with tracer.turn("hola", session_id="sess-abc"):
        tracer.event("gate", {"decision": "skip", "reason": "small talk"})
        tracer.event("llm", {"usage": {"in": 1, "out": 1}})
        tracer.end_turn("hi", iterations=1)

    records = _trace_lines(tmp_path)
    assert [r["type"] for r in records] == ["turn_start", "gate", "llm", "turn_end"]
    # turn_end included: it is written inside the block precisely so it is not
    # the one record that cannot be traced back to its conversation.
    assert {r["session_id"] for r in records} == {"sess-abc"}


def test_turn_id_is_shared_within_a_turn_and_unique_across_turns(
    tmp_path: Path,
) -> None:
    tracer = Tracer(_cfg(tmp_path))
    for _ in range(2):
        with tracer.turn("hola", session_id="sess-abc"):
            tracer.event("tool", {"tool": "x", "output": "ok"})
            tracer.end_turn("hi", iterations=1)

    turn_ids = [r["turn_id"] for r in _trace_lines(tmp_path)]
    first, second = turn_ids[:3], turn_ids[3:]
    assert len(set(first)) == 1 and len(set(second)) == 1
    assert first[0] != second[0], "each turn must be separable within a thread"


def test_events_outside_a_turn_are_still_written_without_a_session(
    tmp_path: Path,
) -> None:
    # Tracing must never be the thing that breaks a caller: a bare event (no
    # surrounding turn) degrades to an unattributed record, not an exception.
    tracer = Tracer(_cfg(tmp_path))
    tracer.event("tool", {"tool": "x", "output": "ok"})

    assert "session_id" not in _trace_lines(tmp_path)[0]


def test_concurrent_turns_do_not_leak_session_ids(tmp_path: Path) -> None:
    """The regression guard for the reason this lives in a ContextVar.

    The Tracer is a process-wide singleton and Cloud Run runs many turns at once
    on one instance. Holding per-turn identity on the instance would let two
    overlapping turns overwrite each other, stamping records with the WRONG
    conversation — misattribution is worse than no session_id, because it is
    silent. Interleave two turns and assert each record kept its own identity.
    """
    tracer = Tracer(_cfg(tmp_path))

    async def one_turn(session_id: str, gap: float) -> None:
        with tracer.turn("hola", session_id=session_id):
            await asyncio.sleep(gap)
            tracer.event("gate", {"decision": "search", "reason": "r"})
            await asyncio.sleep(gap)
            tracer.event("llm", {"usage": {"in": 1, "out": 1}})
            await asyncio.sleep(gap)
            tracer.end_turn("hi", iterations=1)

    async def both() -> None:
        # Different gaps so the two turns genuinely interleave rather than
        # running one after the other.
        await asyncio.gather(one_turn("sess-A", 0.01), one_turn("sess-B", 0.015))

    asyncio.run(both())

    records = _trace_lines(tmp_path)
    assert len(records) == 8
    # The turns really did overlap — otherwise the test proves nothing.
    where = {
        s: [i for i, r in enumerate(records) if r["session_id"] == s]
        for s in ("sess-A", "sess-B")
    }
    assert min(where["sess-B"]) < max(where["sess-A"]), (
        "turns ran sequentially; the test no longer exercises concurrency"
    )
    for session_id in ("sess-A", "sess-B"):
        mine = [r for r in records if r["session_id"] == session_id]
        assert [r["type"] for r in mine] == [
            "turn_start",
            "gate",
            "llm",
            "turn_end",
        ]
        assert len({r["turn_id"] for r in mine}) == 1

    # And the two turns are distinguishable from each other.
    assert len({r["turn_id"] for r in records}) == 2


# ---- the usage ledger -----------------------------------------------------


def test_llm_event_appends_a_usage_ledger_row(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path, model="claude-x"))
    tracer.event("llm", {"usage": {"in": 12, "out": 7}})

    usage = _usage_lines(tmp_path)
    assert len(usage) == 1
    assert usage[0]["model"] == "claude-x"
    assert usage[0]["input_tokens"] == 12
    assert usage[0]["output_tokens"] == 7


def test_usage_rows_are_attributed_to_their_session(tmp_path: Path) -> None:
    # Without this, the ledger answers "how many tokens did the service burn"
    # but never "what did this conversation cost".
    tracer = Tracer(_cfg(tmp_path))
    with tracer.turn("hola", session_id="sess-abc"):
        tracer.event("llm", {"usage": {"in": 12, "out": 7}})
        tracer.end_turn("hi", iterations=1)

    row = _usage_lines(tmp_path)[0]
    assert row["session_id"] == "sess-abc"
    assert row["turn_id"]


def test_non_llm_events_do_not_touch_the_usage_ledger(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path))
    tracer.event("tool", {"tool": "x", "output": "ok"})

    assert _usage_lines(tmp_path) == []


# ---- serverless defaults: no trace dir, OTel off --------------------------


def test_no_trace_dir_writes_no_file_and_never_crashes(tmp_path: Path) -> None:
    # stdout-only mode (the Cloud Run default): a full turn cycle must run
    # without touching the filesystem.
    tracer = Tracer(_cfg(None))
    with tracer.turn("hola"):
        tracer.event("llm", {"usage": {"in": 1, "out": 1}})
    tracer.end_turn("hi", iterations=1)

    assert list(tmp_path.iterdir()) == []


def test_otel_is_off_without_an_endpoint(tmp_path: Path) -> None:
    tracer = Tracer(_cfg(tmp_path))
    assert tracer._otel_tracer is None


# ---- compose --------------------------------------------------------------


def _recorder(store: list[str]) -> Observer:
    def obs(kind: str, event: LoopEvent) -> None:
        store.append(kind)

    return obs


def test_compose_fans_out_to_every_observer_in_order() -> None:
    seen: list[str] = []
    notify = compose(_recorder(seen), _recorder(seen))
    notify("llm", {})

    assert seen == ["llm", "llm"]


def test_compose_drops_none_observers() -> None:
    seen: list[str] = []
    notify = compose(None, _recorder(seen), None)
    notify("tool", {})

    assert seen == ["tool"]


def test_compose_with_all_none_is_a_noop() -> None:
    compose(None, None)("anything", {})  # must not raise
