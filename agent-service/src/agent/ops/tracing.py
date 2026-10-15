"""Trace — one trace per turn (the LLM-Ops box, first step).

The same loop events fan out to up to three sinks:

1. **JSONL, when a trace dir is set (dev):** every turn appends readable lines to
   ``<TRACE_DIR>/<date>.jsonl`` — "what happened, in order", open the file and
   read the agent's mind. Zero dependencies. The container filesystem is
   ephemeral on Cloud Run, so this is a local-dev artifact; in prod point
   ``TRACE_DIR`` at ``/tmp`` or leave it unset.

2. **structlog → stdout, always on (serverless addition):** the same events as
   structured log lines. This is the *durable* path under Cloud Run — stdout is
   collected by Cloud Logging and survives instance recycling, unlike the JSONL
   file. Waku has no equivalent (a local CLI just keeps the file).

3. **OpenTelemetry spans, when OTEL_EXPORTER_OTLP_ENDPOINT is set (prod):** the
   same events as a span tree any OTel backend can render — a local Phoenix
   (``localhost:4317``) or Langfuse cloud (it speaks OTel; point the endpoint +
   auth headers there). The instrumentation below doesn't know or care which.

Two record types are first-class, so the harness's judgment calls can be
read apart from the loop's activity (ADR-0004):

- ``decision`` — one per harness judgment call (``agent/decide/sites.py``):
  the site, the typed answers exactly as the decision model returned them
  (probabilities, labels, confidences), the verdict the harness derived, and
  whether it acted on it. Also appended to ``decisions.jsonl``.
- ``score`` — a number or label attached to a turn or a message: the
  decision model's quality judgement, a user's thumbs up/down, a diagnosis.
  Also appended to ``scores.jsonl``. The shape (``name``, ``value``,
  ``data_type``, ``comment``, ``message_id``) is Langfuse's score object, so
  wiring Langfuse later is a sink, not a redesign.

Provider-neutral by construction (CLAUDE.md §4): the brain never reads
``service.Settings``. The transport builds a :class:`TracerConfig` from its own
settings and injects it — the same pattern as ``MemoryConfig`` / ``DatabaseConfig``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from agent.observability import LoopEvent, Observer

_log = structlog.get_logger("agent.trace")
# A dedicated logger for spend, so token usage can be filtered/aggregated apart
# from the general trace stream (e.g. a Cloud Logging log-based metric on cost).
_usage_log = structlog.get_logger("agent.usage")
# Judgment calls and scores get their own loggers too, for the same reason:
# a log-based metric on "how often does the decision model disagree with the
# chat model" should not have to sift the whole trace stream.
_decision_log = structlog.get_logger("agent.decision")
_score_log = structlog.get_logger("agent.score")

# OpenInference span kinds for the decision sites, so a backend that renders
# them (Phoenix today, Langfuse later) shows a guardrail as a guardrail and a
# judge as an evaluator instead of a generic chain step.
_DECISION_SPAN_KINDS: dict[str, str] = {
    "retrieval": "GUARDRAIL",
    "skill_match": "GUARDRAIL",
    "tool_review": "GUARDRAIL",
    "ask_or_act": "GUARDRAIL",
    "consolidation_gate": "GUARDRAIL",
    "memory_select": "RERANKER",
    "fact_select": "RERANKER",
    "judge": "EVALUATOR",
    "diagnose": "EVALUATOR",
    "skill_proposal": "EVALUATOR",
}


@dataclass(slots=True)
class _Turn:
    """Who this turn belongs to — stamped onto every record it produces.

    ``session_id`` groups the records of one conversation; ``turn_id`` separates
    the turns *within* it, so a long thread stays readable.
    """

    session_id: str | None
    turn_id: str


# Per-turn identity lives in a ContextVar, NOT on the Tracer.
#
# The Tracer is a process-wide singleton (built once in ``build_agent``, shared
# by every request), and Cloud Run serves many requests concurrently per
# instance. Instance attributes would be shared mutable state: two overlapping
# turns would overwrite each other and records would be stamped with the WRONG
# conversation — silent misattribution, strictly worse than no session_id at all.
# asyncio gives each task its own context, so a value set inside one request's
# task is invisible to the others.
_turn: ContextVar[_Turn | None] = ContextVar("agent_turn", default=None)


def _now() -> str:
    """UTC timestamp, millisecond precision, ISO-8601 — the ``ts`` on every trace
    record. Always UTC so events from different Cloud Run instances are directly
    comparable, regardless of each instance's local zone."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _session_attrs(session_id: str | None) -> dict[str, str]:
    """Session identity as OTel span attributes.

    Two keys on purpose, because this module targets two backends (see the
    module docstring): ``langfuse.session.id`` is what Langfuse reads to group
    traces into a session, ``session.id`` is the OpenInference convention a local
    Phoenix reads. Langfuse accepts either; emitting both keeps one code path.
    Langfuse drops session ids over 200 chars — a UUID is far under that.
    """
    if not session_id:
        return {}
    return {"langfuse.session.id": session_id, "session.id": session_id}


@dataclass(frozen=True, slots=True)
class TracerConfig:
    """Tuning for the tracer, injected by the transport (never read from the
    service ``Settings`` directly — CLAUDE.md §4).

    ``model`` / ``provider`` are stamped onto ``llm`` events so a trace records
    which brain answered. ``trace_dir`` is where the local JSONL lands
    (``None`` → JSONL sink off, stdout/OTel only). ``otel_endpoint`` turns the
    span export on when set (``None`` / "" → off).
    """

    model: str
    provider: str = "anthropic"
    trace_dir: Path | None = None
    otel_endpoint: str | None = None


class Tracer:
    """Doubles as a loop Observer: pass ``tracer.event`` anywhere an observer
    goes and every loop step lands in the trace."""

    def __init__(self, config: TracerConfig) -> None:
        self._config = config
        # Divergence from Waku: Waku freezes ``self.path = .../{today}.jsonl`` in
        # the constructor — fine for a short-lived CLI, wrong for a server that
        # lives for days (the filename would stick to the boot date). We store
        # the *directory* here and resolve the dated filename per write instead.
        self._trace_dir = config.trace_dir
        if self._trace_dir is not None:
            # Best-effort, once at boot: create the dir. On a read-only FS this
            # raises loudly here rather than failing silently every turn — point
            # TRACE_DIR at a writable path (e.g. /tmp) or leave it unset.
            self._trace_dir.mkdir(parents=True, exist_ok=True)
        # Set before _init_otel so the attribute always exists (``turn()`` flushes
        # it). _init_otel overwrites it with the real provider when OTel is on.
        self._otel_provider: Any = None
        self._otel_tracer = self._init_otel(config.otel_endpoint)

    def _init_otel(self, endpoint: str | None) -> Any:
        """Wire OTel only if an endpoint is set AND the optional deps are
        installed. Missing deps degrade to JSONL + stdout, never a crash —
        tracing is never allowed to take the service down."""
        if not endpoint:
            return None
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            _log.warning(
                "tracing.otel_deps_missing",
                hint="OTEL endpoint set but opentelemetry not installed; "
                "JSONL + stdout tracing still on.",
            )
            return None
        provider = TracerProvider(
            resource=Resource.create({"service.name": "agent-service"})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
        trace.set_tracer_provider(provider)
        self._otel_provider = provider
        return trace.get_tracer("agent-service")

    def _write(self, record: dict[str, Any]) -> None:
        """Fan one trace record to the durable stdout sink and, when a trace dir
        is configured, append it to today's JSONL file.

        Divergence from Waku: the JSONL filename is resolved *per write*
        (``<dir>/<date>.jsonl``), not frozen at construction — a server runs
        across midnight, so the date must be current at write time. And the whole
        JSONL sink is optional: with ``trace_dir=None`` we emit to stdout only
        (the Cloud Run default), never touching the filesystem.
        """
        record["ts"] = _now()
        # Stamp WHICH conversation this belongs to. All three sinks are flat
        # streams shared by every concurrent turn, so without this a record can
        # only be ordered by ts — never attributed to a thread (CLAUDE.md §2.4:
        # every event lands under a trace id bound to the conversation).
        # Leading position: it is the first thing you look for when reading a
        # trace by eye.
        turn = _turn.get()
        if turn is not None:
            record = {
                "session_id": turn.session_id,
                "turn_id": turn.turn_id,
                **record,
            }
        # Sink 1 — structlog → stdout: the durable path under Cloud Run (collected
        # by Cloud Logging, survives instance recycling). Always on.
        _log.info("trace", **record)
        # Sink 2 — local JSONL, dev only. Skipped entirely when no dir is set.
        if self._trace_dir is None:
            return
        path = self._trace_dir / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _append_ledger(self, filename: str, record: dict[str, Any]) -> None:
        """Append one record to a dedicated JSONL ledger next to the trace
        file (``usage.jsonl``, ``decisions.jsonl``, ``scores.jsonl``). Off
        when no trace dir is set — stdout already carries the record."""
        if self._trace_dir is None:
            return
        record = {**record, "ts": _now()}
        with (self._trace_dir / filename).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _record_decision(self, event: LoopEvent) -> None:
        """One harness judgment call. Stamped with the turn like every trace
        record, then appended to the ``decisions.jsonl`` ledger so the
        decision model's behaviour can be aggregated per site without
        parsing the whole trace."""
        turn = _turn.get()
        record: dict[str, Any] = {
            "session_id": turn.session_id if turn else None,
            "turn_id": turn.turn_id if turn else None,
            **event,
        }
        _decision_log.info("decision", **record)
        self._append_ledger("decisions.jsonl", record)

    def _record_usage(self, event: LoopEvent) -> None:
        """One LLM call's token usage — the running record of what was spent.

        Dual sink, same as the trace stream but to a dedicated ``usage.jsonl``
        ledger so spend can be aggregated apart from traces:

        - **stdout** (``agent.usage`` logger), always on: the durable path under
          Cloud Run — Cloud Logging retains it, and a Log Router sink can export
          it to a GCS bucket with zero app code.
        - **``usage.jsonl`` file**, only when a trace dir is set: dev-local by
          default, but bucket-ready — point ``TRACE_DIR`` at a mounted GCS bucket
          (Cloud Storage FUSE) and the ledger lands straight in the bucket.

        Langfuse (OTel) also captures usage on the ``llm`` span when enabled.
        Tokens are the ground truth; dollar cost is derived downstream from
        provider+model (pricing changes). A first-class Postgres ledger is a later
        decision (its own ADR)."""
        usage = event.get("usage", {})
        turn = _turn.get()
        record: dict[str, Any] = {
            # Spend is only actionable if it can be attributed: session_id is what
            # turns this ledger from "how many tokens did the service burn" into
            # "what did this conversation cost".
            "session_id": turn.session_id if turn else None,
            "turn_id": turn.turn_id if turn else None,
            "provider": self._config.provider,
            "model": self._config.model,
            "kind": "loop",
            "input_tokens": usage.get("in", 0),
            "output_tokens": usage.get("out", 0),
        }
        # Sink 1 — stdout (structlog stamps its own timestamp).
        _usage_log.info("usage", **record)
        # Sink 2 — the JSONL ledger, dev-local or bucket-mounted. Off when unset.
        if self._trace_dir is None:
            return
        record["ts"] = _now()
        with (self._trace_dir / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def event(self, kind: str, event: LoopEvent) -> None:
        if kind == "text":
            return  # streaming token deltas are for the live UI, not the trace
        if kind == "llm":
            self._record_usage(event)
            # stamp WHICH brain answered — a trace without the model is half a
            # trace once there's more than one model in play.
            event = {
                "provider": self._config.provider,
                "model": self._config.model,
                **event,
            }
        if kind == "decision":
            self._record_decision(event)
        if kind == "score":
            # Scores emitted mid-turn (the judge) ride the observer like any
            # event; ``score()`` below is the same path for out-of-turn ones.
            self._record_score(event)
        self._write({"type": kind, **event})
        turn = _turn.get()
        if self._otel_tracer and turn is not None:
            label = (
                f"{kind}.{event.get('tool', event.get('site', event.get('name', '')))}"
            )
            label = label.rstrip(".")
            span_kind = {"llm": "LLM", "tool": "TOOL", "score": "EVALUATOR"}.get(
                kind, "CHAIN"
            )
            if kind == "decision":
                span_kind = _DECISION_SPAN_KINDS.get(str(event.get("site")), "CHAIN")
            with self._otel_tracer.start_as_current_span(
                label,
                attributes={
                    "openinference.span.kind": span_kind,
                    # On every span, not just the root: Langfuse filters and
                    # aggregates per observation, so a session attribute that
                    # lives only on the root leaves child spans unattributed.
                    # Parenting still comes from OTel's own context — these spans
                    # nest under the turn's root span automatically.
                    **_session_attrs(turn.session_id),
                    "agent.turn_id": turn.turn_id,
                    **{
                        f"agent.{k}": json.dumps(v, default=str)
                        for k, v in event.items()
                    },
                },
            ):
                pass

    def _record_score(self, event: LoopEvent) -> None:
        turn = _turn.get()
        record: dict[str, Any] = {
            "session_id": event.get("session_id")
            or (turn.session_id if turn else None),
            "turn_id": turn.turn_id if turn else None,
            **{k: v for k, v in event.items() if k != "session_id"},
        }
        _score_log.info("score", **record)
        self._append_ledger("scores.jsonl", record)

    def score(
        self,
        name: str,
        value: float | str | bool,
        *,
        message_id: str | None,
        session_id: str | None = None,
        source: str,
        comment: str | None = None,
        data_type: str | None = None,
    ) -> None:
        """Attach a score to a message — the one trace record that can be
        written *outside* a turn (a thumbs-down arrives minutes later, from a
        different request). ``session_id`` is therefore explicit here; inside
        a turn it is inferred like everything else.

        Mirrors Langfuse's score fields one to one (``name``, ``value``,
        ``data_type`` NUMERIC / CATEGORICAL / BOOLEAN, ``comment``), keyed by
        the assistant ``message_id`` the feedback endpoint already uses.
        """
        if data_type is None:
            data_type = (
                "BOOLEAN"
                if isinstance(value, bool)
                else "NUMERIC"
                if isinstance(value, int | float)
                else "CATEGORICAL"
            )
        event: LoopEvent = {
            "name": name,
            "value": value,
            "data_type": data_type,
            "source": source,
            "message_id": message_id,
            "comment": comment,
        }
        if session_id is not None:
            event["session_id"] = session_id
        self._record_score(event)
        # Keep the explicit session_id in the trace record too: outside a
        # turn, _write has no turn binding to stamp it from.
        self._write({"type": "score", **event})
        if self._otel_tracer is not None and _turn.get() is not None:
            with self._otel_tracer.start_as_current_span(
                f"score.{name}",
                attributes={
                    "openinference.span.kind": "EVALUATOR",
                    **{
                        f"agent.score.{k}": json.dumps(v, default=str)
                        for k, v in event.items()
                    },
                },
            ):
                pass

    @contextmanager
    def turn(
        self, user_message: str, session_id: str | None = None
    ) -> Iterator[Tracer]:
        """Bracket one turn, binding it to its conversation.

        Everything traced inside the block — by this task, at any depth — is
        stamped with ``session_id`` and a fresh ``turn_id``. ``session_id`` is
        optional so a bare ``Tracer`` still works in tests and one-off scripts;
        in the service it is always passed.

        ``end_turn`` must be called *inside* this block: the binding is released
        on exit, and a ``turn_end`` written afterwards would be the one record
        that cannot be attributed to its conversation.
        """
        turn = _Turn(session_id=session_id, turn_id=uuid.uuid4().hex)
        token = _turn.set(turn)
        try:
            self._write({"type": "turn_start", "user_message": user_message})
            if self._otel_tracer:
                with self._otel_tracer.start_as_current_span(
                    "agent_run",
                    attributes={
                        "openinference.span.kind": "AGENT",
                        "agent.user_message": user_message,
                        **_session_attrs(session_id),
                        # On the root too, not just the children: filtering a
                        # backend by turn_id must return the whole turn,
                        # including the span that opened it.
                        "agent.turn_id": turn.turn_id,
                    },
                ):
                    yield self
            else:
                yield self
        finally:
            _turn.reset(token)
            # Flush here, not in end_turn: the root span is closed by the time
            # this runs, so the exporter actually ships it. A per-turn flush means
            # the turn survives even a killed instance (Cloud Run recycles freely).
            if self._otel_provider is not None:
                self._otel_provider.force_flush(timeout_millis=2000)

    def end_turn(self, reply: str, iterations: int) -> None:
        """Close the turn's record. Call inside the ``turn()`` block — see there."""
        self._write({"type": "turn_end", "reply": reply, "iterations": iterations})


def compose(*observers: Observer | None) -> Observer:
    """Fan one loop event out to several observers (the caller's stream + the
    tracer + the gate-decision capture). Falsy entries — a caller that passed no
    observer — are dropped here, so the loop threads a single ``notify`` and
    doesn't null-check or know how many observers sit behind it."""
    active = [o for o in observers if o is not None]

    def fanout(kind: str, event: LoopEvent) -> None:
        for obs in active:
            obs(kind, event)

    return fanout
