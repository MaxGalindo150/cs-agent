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

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import (
    MessageParam,
    RedactedThinkingBlockParam,
    TextBlockParam,
    ThinkingBlockParam,
    ToolUseBlockParam,
)
from pydantic import BaseModel, ValidationError

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
from agent.vision import Image

log = structlog.get_logger()

# Keyed by the block's own "type" discriminant, not by its response-side
# Python class — a streamed response can hand back a subclass (e.g.
# ``ParsedTextBlock`` for ``type: "text"``) carrying response-only fields
# (``parsed_output``) that the *input*-side Param TypedDict below has never
# heard of. Whitelisting by what the Param type declares (rather than by
# whatever the response object happens to declare) is what actually matches
# the schema the API validates against when this block is replayed as input.
_CONTENT_BLOCK_INPUT_KEYS: dict[str, frozenset[str]] = {
    "text": frozenset(TextBlockParam.__annotations__),
    "tool_use": frozenset(ToolUseBlockParam.__annotations__),
    "thinking": frozenset(ThinkingBlockParam.__annotations__),
    "redacted_thinking": frozenset(RedactedThinkingBlockParam.__annotations__),
}


def _user_content(text: str, images: list[Image] | None) -> str | list[dict[str, Any]]:
    """The LLM-facing content for this turn: plain text normally, or a text
    block plus one image block per attachment. Built fresh per call — never
    persisted (see ``_with_image_marker``) and never carried into a later
    turn's history, so a conversation's cost/size doesn't grow with every
    image a customer ever sent, only the one just attached."""
    if not images:
        return text
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    blocks.extend(
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.media_type,
                "data": img.data,
            },
        }
        for img in images
    )
    return blocks


def _with_image_marker(text: str, images: list[Image] | None) -> str:
    """What gets persisted/replayed instead of the raw image: a short note,
    not the bytes — Postgres's ``chat_messages.content`` would otherwise
    balloon, and every later turn's working memory would re-send it forever
    (the same reasoning as truncating a tool's output, see
    ``agent/runtime/session.py``)."""
    if not images:
        return text
    noun = "image" if len(images) == 1 else "images"
    return f"{text}\n[{len(images)} {noun} attached]"


def _serialize_tail(tail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`run_loop` appends the assistant's turn as ``response.content`` verbatim
    (real Anthropic SDK objects — ``TextBlock``/``ToolUseBlock`` pydantic
    models, not dicts) — a captured tail can carry those straight through.
    Convert them to plain JSON-able dicts before this goes into a JSONB
    column; entries built by this module (the original user message, a
    tool_result) are already plain dicts and pass through unchanged.

    A streamed response can hand back a block whose Python class carries
    fields the corresponding *input* Param TypedDict has never heard of — e.g.
    a text block streamed back while tools are in play arrives as
    ``ParsedTextBlock`` (a ``TextBlock`` subclass) with its own declared
    ``parsed_output`` field. A plain ``model_dump()`` includes it, and the
    API's input-side schema (``TextBlockParam``) rejects it outright with a
    400 when this tail is replayed on resume — filtering by *that* block's own
    fields doesn't help, since the field is legitimately declared there, just
    not on the Param type. Whitelist by the block's ``type`` discriminant
    against ``_CONTENT_BLOCK_INPUT_KEYS`` (the Param side) instead.
    """
    serialized: list[dict[str, Any]] = []
    for msg in tail:
        content = msg.get("content")
        if not isinstance(content, list):
            serialized.append(msg)
            continue
        blocks: list[Any] = []
        for block in content:
            if not isinstance(block, BaseModel):
                blocks.append(block)
                continue
            dumped = block.model_dump(mode="json")
            allowed = _CONTENT_BLOCK_INPUT_KEYS.get(dumped.get("type", ""))
            if allowed is not None:
                dumped = {k: v for k, v in dumped.items() if k in allowed}
            blocks.append(dumped)
        serialized.append({**msg, "content": blocks})
    return serialized


def _sanitize_tail(tail: list[dict[str, Any]], plain_text: str) -> list[dict[str, Any]]:
    """A captured suspended-turn tail (``LoopResult.suspended["turn_tail"]``)
    starts with this leg's own triggering message — a plain new turn's user
    message, or (on a re-suspended resume) a tool_result closing the previous
    one. Only the former can ever carry raw image blocks (`_user_content`);
    swap it for the same marker text already used for `chat_messages.content`
    (`_with_image_marker`) so an image never outlives the single request it
    arrived in, suspended turn or not. Left unchanged when the first entry
    has no image block — including every tool_result-first tail, which never
    does."""
    if not tail:
        return []
    first = tail[0]
    content = first.get("content")
    has_image = isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "image" for b in content
    )
    if not has_image:
        return tail
    return [{"role": first["role"], "content": plain_text}, *tail[1:]]


def _tool_status(out: str) -> str:
    """A tool's output, classified for `meta.tools` — a coarse "did it work"
    signal a reopened thread's UI can show without parsing the full text."""
    low = (out or "").lower()
    return (
        "error"
        if ("failed" in low or "timed out" in low or low.startswith("error"))
        else "ok"
    )


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


class SuspendedToolUse(BaseModel):
    """Validated shape of ``chat_sessions.suspended_tool_use``.

    Untrusted at this boundary — a free-form JSONB value that could have been
    written by a previously deployed version of this code with a different
    shape. Parsed once, here, rather than subscripting ``pending[...]`` field
    by field: a malformed row must degrade to a fresh turn, not raise a
    ``KeyError`` that leaves the suspension neither claimed nor resumed —
    which would make ``peek_suspended_tool_use`` return that same unreadable
    payload on every later turn, wedging the conversation permanently."""

    tool_use_id: str
    tool_name: str
    turn_tail: list[dict[str, Any]]
    system: str
    payload: dict[str, Any]
    iteration: int


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
        user_message: str | None = None,
        choice_id: str | None = None,
        observer: Observer | None = None,
        source: str = "api",
        stream: bool = False,
        principal: Principal | None = None,
        images: list[Image] | None = None,
    ) -> LoopResult:
        """One full turn: assemble working memory → run the loop → persist.

        ``choice_id`` resolves a pending `present_choice` suspension
        (``agent/tools/implementations/present_choice.py``) by option id —
        exactly one of ``user_message``/``choice_id`` is expected (the
        transport validates this; see ``service/api/v1/chat.py::ChatRequest``).
        When a suspension is pending, this branches to
        ``_resume_suspended_turn`` before ever touching ``build_system()`` or
        ``run_loop`` the normal way — see that method for why a button click
        and free text take different paths.

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

        ``images`` are attached as vision context for THIS call only — never
        persisted or replayed into a later turn's working memory (see
        ``_user_content``/``_with_image_marker``); what's recorded instead is
        a short marker noting how many arrived.

        Before any of that: ``session.fixed_response()`` may short-circuit the
        whole turn (e.g. an already-escalated session) — the message is still
        recorded, but the LLM/tools never run and a canned reply goes out
        instead. See ``agent/runtime/session.py`` for why this must be a
        harness guarantee, not a prompt instruction the model could ignore.
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
        ctx = ToolContext(principal=principal, session_id=session_id)
        persisted_message = _with_image_marker(user_message or "", images)

        with self._tracer.turn(persisted_message, session_id=str(session_id)):
            # No held session (unlike Waku): build one per request and load this
            # conversation's recent history from Postgres before assembling the
            # prompt. Discarded when the turn ends — nothing conversation-specific
            # lives in the process between requests (CLAUDE.md §9).
            session = Session(session_id, memory=self._memory)
            await session.switch(session_id, self._config.history_turns)

            # A deterministic gate, checked before the LLM ever runs: once a
            # session is escalated (or a future fixed_response case matches),
            # the model never gets another turn to reason about it — it can't
            # repeat a promise it can't back. The message is still recorded
            # (the human agent needs the full transcript), just never sent
            # to run_loop.
            fixed = await session.fixed_response(user_message or "")
            if fixed is not None:
                notify("text", {"delta": fixed})
                await session.add_exchange(
                    persisted_message,
                    fixed,
                    source=source,
                    meta={
                        "fixed_response": True,
                        "segments": [{"type": "text", "text": fixed}],
                    },
                )
                self._tracer.end_turn(fixed, 0)
                return LoopResult(reply=fixed, tool_calls=[], iterations=0)

            # A suspended `present_choice` (agent/tools/registry.py's
            # Tool.suspends) takes over the whole turn — never build_system()
            # or run_loop() the normal way until it's resolved one way or
            # another. See _resume_suspended_turn for the button-vs-free-text
            # branch and why only one of them rebuilds the system prompt.
            pending = await self._memory.peek_suspended_tool_use(session_id)
            if pending is not None:
                resumed = await self._resume_suspended_turn(
                    session,
                    session_id,
                    pending,
                    user_message,
                    choice_id,
                    notify,
                    source,
                    stream,
                    ctx,
                )
                if resumed is not None:
                    return resumed
                # else: lost a race to a concurrent duplicate request — the
                # suspension is gone. Fall through only if there's real text
                # to run a fresh turn on (checked next); a bare stale
                # `choice_id` with nothing else has nothing left to do.

            if not user_message:
                # `choice_id` was given but nothing (or nothing anymore) is
                # pending for it to resolve — never run a turn with no real
                # message content (build_system/run_loop both expect one).
                reply = (
                    "This has already been answered, or there's nothing "
                    "pending to answer — what do you need?"
                )
                notify("text", {"delta": reply})
                self._tracer.end_turn(reply, 0)
                return LoopResult(reply=reply)

            user_id = principal.user_id if principal else None
            system = await session.build_system(user_message, user_id, notify=notify)

            # session.history is list[dict]; the loop wants the SDK's MessageParam.
            # Cast at this boundary (as the loop casts its tool schemas) — the
            # runtime shapes match, only the static type differs. Only THIS
            # entry may carry image blocks — session.history's prior turns are
            # always plain text (see _user_content/_with_image_marker above).
            history_len = len(session.history)  # where this turn's own content starts
            messages = cast(
                "list[MessageParam]",
                session.history
                + [{"role": "user", "content": _user_content(user_message, images)}],
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

            meta: dict[str, Any] = {
                "gate": captured.get("gate"),
                "iterations": result.iterations,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "tools": [
                    {"tool": c["tool"], "status": _tool_status(c["output"])}
                    for c in result.tool_calls
                ],
                # The ordered text/tool-call trail, so a reopened thread can
                # render tool activity inline between the sentences that
                # surrounded it instead of collapsing everything above the
                # final text (see frontend/src/lib/chat/types.ts::MessagePart).
                "segments": result.segments,
                # which brain answered this turn — so a reopened thread (or a
                # thread you switched models mid-way) shows it per card.
                "model": self._config.model,
                "provider": self._config.provider,
            }

            if result.suspended is not None:
                # Everything appended since this turn started (not just the
                # final assistant message) — an earlier tool call in the same
                # turn must survive on resume too (see the plan's note on why
                # a single-message snapshot isn't enough). Sanitized: the first
                # entry is this turn's own trigger message, which may carry
                # raw image blocks that must not outlive this one request.
                result.suspended["turn_tail"] = _sanitize_tail(
                    _serialize_tail(
                        cast("list[dict[str, Any]]", messages[history_len:])
                    ),
                    persisted_message,
                )
                meta["tool_use_id"] = result.suspended["tool_use_id"]
                await session.add_exchange(
                    persisted_message,
                    result.reply,
                    tool_calls=result.tool_calls,
                    source=source,
                    meta=meta,
                )
                await self._memory.set_suspended_tool_use(session_id, result.suspended)
                self._tracer.end_turn(result.reply, result.iterations)
                return result

            await session.add_exchange(
                persisted_message,
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

    async def _resume_suspended_turn(
        self,
        session: Session,
        session_id: uuid.UUID,
        pending: dict[str, Any],
        user_message: str | None,
        choice_id: str | None,
        notify: Observer,
        source: str,
        stream: bool,
        ctx: ToolContext,
    ) -> LoopResult | None:
        """Resolve a pending `present_choice` (or decide there's nothing here
        that resolves it yet). Two resolution paths:

        - **Button click** (`choice_id` matches one of the pending options):
          replay the ENTIRE `system` string built for the turn that asked the
          question — soul + retrieved memory + matched skill instructions,
          not just the soul — verbatim. `build_system()` is never called on
          this path: the retrieval gate and skill matcher already decided
          everything relevant to this exact question a moment ago; rebuilding
          either on a bare option id would be wrong, not just wasteful.
        - **Free text** (customer types instead of clicking): the full normal
          pipeline runs — `build_system()` fresh against what they typed,
          same as any ordinary new turn — because it's genuinely new input
          the gate/skill matcher should see. The dangling tool_use still has
          to be closed first (Anthropic requires a tool_result immediately
          after it): the customer's text becomes that tool_result's content.

        Returns `None` only when a concurrent request already claimed this
        suspension (double-submit/retry) — `respond()` decides what happens
        next in that case. Every other outcome here is final (persistence and
        tracing already done).
        """
        try:
            state = SuspendedToolUse.model_validate(pending)
        except ValidationError as exc:
            # This version can't read the persisted shape — never let that
            # wedge the conversation forever (see SuspendedToolUse's
            # docstring). Best-effort clear: if `tool_use_id` itself didn't
            # survive validation there's nothing left to key the claim on,
            # and the next peek will just hit this same path again.
            log.error(
                "suspension.unreadable", session_id=str(session_id), error=str(exc)
            )
            stale_id = pending.get("tool_use_id")
            if isinstance(stale_id, str):
                await self._memory.claim_suspended_tool_use(session_id, stale_id)
            return None

        options = state.payload.get("options", [])
        matched = (
            next((o for o in options if o.get("id") == choice_id), None)
            if choice_id
            else None
        )

        if matched is None and not user_message:
            # A stale/invalid choice_id with nothing else — reject it without
            # touching the still-live suspension, so a real retry can still
            # resolve it (docs/SECURITY.md-style: never trust a client id).
            reply = "Please choose one of the options above, or tell me what you need."
            notify("text", {"delta": reply})
            self._tracer.end_turn(reply, 0)
            return LoopResult(reply=reply)

        # Only claim (clear) the suspension once we're sure this request
        # actually resolves it — never as a side effect of merely checking.
        claimed = await self._memory.claim_suspended_tool_use(
            session_id, state.tool_use_id
        )
        if not claimed:
            return None  # lost a race — caller decides what happens next

        tool_use_id = state.tool_use_id
        logged_user_text = (
            f"[selected option: {matched['label']}]"
            if matched is not None
            else (user_message or "")
        )

        # A hard budget, same as run_loop's own guardrail: if the question
        # that suspended was already asked in this turn's last allowed
        # iteration (or max_iterations shrank since), resuming would call the
        # LLM with a non-positive budget and just return the generic
        # "iteration limit" reply — silently truncating instead of escalating
        # (CLAUDE.md §2.3). Escalate deterministically instead.
        remaining_iterations = self._config.max_iterations - state.iteration
        if remaining_iterations <= 0:
            await self._memory.mark_escalated(
                session_id, "Ran out of turns while resuming a paused question."
            )
            reply = (
                "Necesito que un agente humano continúe con esto — ya quedó "
                "marcado, en breve alguien te da seguimiento."
            )
            notify("text", {"delta": reply})
            await session.add_exchange(
                logged_user_text,
                reply,
                source=source,
                meta={"segments": [{"type": "text", "text": reply}]},
            )
            await self._memory.mark_choice_resolved(
                session_id, tool_use_id, matched["id"] if matched is not None else None
            )
            self._tracer.end_turn(reply, 0)
            return LoopResult(reply=reply)

        t0 = time.perf_counter()
        if matched is not None:
            system = state.system
            resolution_text = f"The customer selected: {matched['label']}"
        else:
            assert user_message is not None  # guaranteed by the guard above
            user_id = ctx.principal.user_id if ctx.principal else None
            system = await session.build_system(user_message, user_id, notify=notify)
            resolution_text = user_message

        baseline = cast("list[MessageParam]", session.history[:-2] + state.turn_tail)
        history_len = len(baseline)
        messages = list(baseline) + [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": resolution_text,
                    }
                ],
            }
        ]

        result = await run_loop(
            client=self._client,
            model=self._config.model,
            system=system,
            messages=messages,
            tools=self._tools,
            max_iterations=remaining_iterations,
            max_tokens=self._config.max_tokens,
            observer=notify,
            stream=stream,
            ctx=ctx,
        )

        meta: dict[str, Any] = {
            "iterations": result.iterations,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "tools": [
                {"tool": c["tool"], "status": _tool_status(c["output"])}
                for c in result.tool_calls
            ],
            "segments": result.segments,
            "model": self._config.model,
            "provider": self._config.provider,
        }

        if result.suspended is not None:
            # Asked another clarifying question right after this one resolved.
            # The new leg's tail must start the same way a FRESH suspension's
            # does — a plain user-facing message, never the tool_result we
            # just synthesized above: that tool_result's matching tool_use
            # only exists in this one resume call's in-memory `messages`,
            # never in the persisted (summarized-to-text) session.history:
            # replaying it verbatim on the *next* resume would leave an
            # orphaned tool_result with no preceding tool_use, and the API
            # would reject the whole request with a 400.
            resumed_leg_tail = [
                {"role": "user", "content": logged_user_text},
                *messages[history_len + 1 :],
            ]
            result.suspended["turn_tail"] = _sanitize_tail(
                _serialize_tail(cast("list[dict[str, Any]]", resumed_leg_tail)),
                logged_user_text,
            )
            meta["tool_use_id"] = result.suspended["tool_use_id"]
            await session.add_exchange(
                logged_user_text,
                result.reply,
                tool_calls=result.tool_calls,
                source=source,
                meta=meta,
            )
            await self._memory.set_suspended_tool_use(session_id, result.suspended)
            # This leg's own question is answered too — just by one that
            # immediately led to another, rather than a final reply. Settle
            # it the same way, so a reload shows THIS leg's buttons resolved
            # instead of still live.
            await self._memory.mark_choice_resolved(
                session_id, tool_use_id, matched["id"] if matched is not None else None
            )
            self._tracer.end_turn(result.reply, result.iterations)
            return result

        await session.add_exchange(
            logged_user_text,
            result.reply,
            tool_calls=result.tool_calls,
            source=source,
            meta=meta,
        )
        # Both paths settle the question: a click names the option, typed
        # text only records that the buttons are no longer live.
        await self._memory.mark_choice_resolved(
            session_id, tool_use_id, matched["id"] if matched is not None else None
        )
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
