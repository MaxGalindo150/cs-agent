"""Turn orchestration — the serverless analog of Waku's ``app.py``.

In Waku, ``app.py`` is *both* the assembly diagram (config → db → tools → memory
→ session → loop) *and* the per-turn orchestrator, held together by a long-lived
``Waku`` object. Here those two jobs are split, on purpose:

- **Assembly lives in the transport.** ``service/main.py`` (lifespan) reads the
  service ``Settings`` and builds the process-wide singletons — the LLM client,
  the ``Database`` pool, ``Memory``, the tool registry, the ``Tracer`` — then
  injects them here. The brain never imports ``service`` nor reads its
  ``Settings`` (CLAUDE.md §4); it receives only the values it needs, as
  ``AgentConfig`` (the same pattern as ``MemoryConfig`` / ``DatabaseConfig``).

- **This file is the orchestrator.** ``Agent`` holds those injected singletons
  and exposes ``respond()`` (one full turn). Unlike ``Waku`` it does **not** hold
  a ``Session``: session state lives in Postgres and is rebuilt per request, so
  the request path stays stateless under Cloud Run autoscaling (CLAUDE.md §9).

Resource ownership follows the same split — the pool, the LLM client, and the
BNPL client are opened and closed by the lifespan, not here. ``Agent`` is a pure
consumer; it owns nothing it would need to close.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from agent.identity import Principal
from agent.loop.agent import LoopResult, run_loop
from agent.memory import Memory, MemoryConfig
from agent.memory.db import Database
from agent.memory.embeddings import Embedder
from agent.observability import LoopEvent, Observer
from agent.ops.tracing import Tracer, TracerConfig, compose
from agent.runtime.session import Session
from agent.tools.context import ToolContext
from agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Tuning knobs the brain needs, injected by the transport.

    Mirrors Waku's ``Settings`` fields that ``respond()`` actually reads, minus
    everything transport- or filesystem-specific (there is no ``home`` here).
    The transport fills these from its own ``Settings`` at wiring time; the brain
    never sees ``service.core.config.Settings`` (CLAUDE.md §4).
    """

    model: str
    """``ANTHROPIC_CHAT_MODEL`` — which model reasons this turn."""

    max_iterations: int = 10
    """Loop guardrail: hard cap on reason→act cycles, so a turn never spins
    forever (the loop's exit condition #2)."""

    max_tokens: int = 2048
    """Ceiling on output tokens per LLM call — a cost/latency bound, not a
    target."""

    history_turns: int = 12
    """Sliding window of working memory: only the last N turns (2 rows each)
    enter the prompt, so context/cost/latency stay flat no matter how long the
    conversation runs. Older turns live in Postgres and return via the retrieval
    gate + episodic memory when relevant."""

    provider: str = "anthropic"
    """Stamped into each turn's ``meta`` so a reopened thread records which
    provider answered. A single provider today; kept explicit for parity with
    Waku's multi-provider traces."""


class Agent:
    """Serverless analog of Waku's ``Waku``: holds the process-wide singletons
    (client, memory, tools, tracer) built once at startup and injected here.

    Deliberately holds **no** ``Session`` — session state is loaded from Postgres
    per request inside ``respond()`` and discarded when the turn ends, so nothing
    conversation-specific lives in the process between requests (CLAUDE.md §9).
    """

    def __init__(
        self,
        client: AsyncAnthropic,
        memory: Memory,
        tools: ToolRegistry,
        tracer: Tracer,
        config: AgentConfig,
    ) -> None:
        self._client = client
        self._memory = memory
        self._tools = tools
        self._tracer = tracer
        self._config = config

    async def start_session(
        self, title: str | None = None, principal: Principal | None = None
    ) -> uuid.UUID:
        """Create a fresh conversation and return its id. The transport calls this
        when a request arrives with no ``session_id`` (a 'new chat'); the client
        then echoes the id back on later turns to continue the thread.

        ``principal`` is unwrapped to a plain ``user_id`` string here — the
        one seam between the identity type and the memory facade, which never
        imports ``agent.identity`` (CLAUDE.md §4)."""
        user_id = principal.user_id if principal else None
        return await self._memory.create_session(title, user_id=user_id)

    async def respond(
        self,
        session_id: uuid.UUID,
        user_message: str,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
        principal: Principal | None = None,
    ) -> LoopResult:
        """One full turn: assemble working memory → run the loop → persist.

        ``session_id`` says which conversation this turn belongs to. Waku reads
        it off ``self.session`` (held on the long-lived object); here the ``Agent``
        holds no session, so the caller passes it and we rebuild a ``Session``
        per request — loading its recent history from Postgres and discarding it
        when the turn ends, so nothing conversation-specific lives in the process
        (CLAUDE.md §9). The session row must already exist (created up front by
        the transport); ``chat_messages`` FKs to it.

        ``source`` tags which channel the message arrived through (webchat /
        whatsapp / …) so the unified chat can show its origin. ``stream=True``
        streams the reply text token by token to the observer. Everything that
        happens is both shown (observer) and recorded (tracer).

        ``principal`` is the identified end-user this turn is for (or ``None``
        for an anonymous visitor) — wrapped once, here, into the ``ToolContext``
        the loop forwards opaquely to ``ToolRegistry.execute``.
        """
        captured: dict[str, Any] = {}

        def _capture(kind: str, ev: LoopEvent) -> None:
            if kind == "gate":
                captured["gate"] = {
                    "decision": ev.get("decision"),
                    "reason": ev.get("reason"),
                }

        notify = compose(observer, self._tracer.event, _capture)
        t0 = time.perf_counter()
        ctx = ToolContext(principal=principal)

        with self._tracer.turn(user_message, session_id=str(session_id)):
            # No held session (unlike Waku): build one per request and load this
            # conversation's recent history from Postgres before assembling the
            # prompt. Discarded when the turn ends — nothing conversation-specific
            # lives in the process between requests (CLAUDE.md §9).
            session = Session(session_id, memory=self._memory)
            await session.switch(session_id, self._config.history_turns)
            user_id = principal.user_id if principal else None
            system = await session.build_system(user_message, user_id, notify=notify)

            # session.history is list[dict]; the loop wants the SDK's MessageParam.
            # Cast at this boundary (as the loop casts its tool schemas) — the
            # runtime shapes match, only the static type differs.
            messages = cast(
                "list[MessageParam]",
                session.history + [{"role": "user", "content": user_message}],
            )

            result = await run_loop(
                client=self._client,
                model=self._config.model,
                system=system,
                messages=messages,
                tools=self._tools,
                max_iterations=self._config.max_iterations,
                max_tokens=self._config.max_tokens,
                observer=notify,
                stream=stream,
                ctx=ctx,
            )

            def _status(out: str) -> str:
                low = (out or "").lower()
                return (
                    "error"
                    if (
                        "failed" in low or "timed out" in low or low.startswith("error")
                    )
                    else "ok"
                )

            meta = {
                "gate": captured.get("gate"),
                "iterations": result.iterations,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "tools": [
                    {"tool": c["tool"], "status": _status(c["output"])}
                    for c in result.tool_calls
                ],
                # which brain answered this turn — so a reopened thread (or a
                # thread you switched models mid-way) shows it per card.
                "model": self._config.model,
                "provider": self._config.provider,
            }
            await session.add_exchange(
                user_message,
                result.reply,
                tool_calls=result.tool_calls,
                source=source,
                meta=meta,
            )

            # Consolidation is intentionally NOT run here: on serverless it moves
            # to an async worker (CLAUDE.md §4), off the request hot path — an
            # extra LLM call per turn would blow the latency/cost budget. Waku's
            # export_markdown (a human-readable MEMORY.md mirror) has no home on an
            # ephemeral FS; revisit if we ever want it in a bucket.

            # Inside the block on purpose: the turn's session binding is released
            # on exit, so a turn_end written outside would be the only record
            # missing its session_id. The OTel flush moved into turn()'s cleanup.
            self._tracer.end_turn(result.reply, result.iterations)

        return result


def build_agent(
    *,
    client: AsyncAnthropic,
    db: Database,
    tools: ToolRegistry,
    chat_model: str,
    fast_model: str,
    trace_dir: Path | None = None,
    otel_endpoint: str | None = None,
    embedder: Embedder | None = None,
    max_iterations: int = 10,
    max_tokens: int = 2048,
    history_turns: int = 12,
    provider: str = "anthropic",
) -> Agent:
    """Assemble an ``Agent`` from its parts — the single place ``Memory`` +
    ``Tracer`` + ``Agent`` are wired together, shared by the transport lifespan
    and the test harness so the two never drift.

    Reads no ``Settings``: the caller injects the values it needs (CLAUDE.md §4).
    This is the serverless mirror of the ``self.memory = Memory(...)`` /
    ``self.tracer = Tracer(...)`` lines in Waku's ``Waku.__init__`` — the one spot
    where the memory pillars (semantic / episodic / procedural) come into being.
    """
    memory = Memory(db, client, MemoryConfig(fast_model=fast_model), embedder=embedder)
    tracer = Tracer(
        TracerConfig(model=chat_model, trace_dir=trace_dir, otel_endpoint=otel_endpoint)
    )
    return Agent(
        client=client,
        memory=memory,
        tools=tools,
        tracer=tracer,
        config=AgentConfig(
            model=chat_model,
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            history_turns=history_turns,
            provider=provider,
        ),
    )
