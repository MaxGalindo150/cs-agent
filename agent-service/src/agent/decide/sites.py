"""Decision sites — every judgment call the harness makes, in one place.

The loop, the memory facade, the session, the consolidation worker and the
feedback endpoint each hit a moment where the harness has to *decide*
something narrow before it can continue. Each of those moments is a method
here, with the same three properties:

1. **Typed questions, calibrated answers.** A site asks the :class:`Decider`
   ``noul`` / ``choice`` / ``score`` questions and reads typed answers back.
   A ``choice``/``score`` is acted on only above
   ``DecisionConfig.confidence_threshold``; below it the site takes its
   fallback — the behaviour the harness had before this module existed.
   Unsure is a valid outcome, never a coin flip.

2. **Jev suggests; the chat model decides.** No site forces a tool, rewrites
   a reply or routes to a sub-agent. The loop sites (``tool_review``,
   ``ask_or_act``) return a *suggestion* the loop hands the model once as a
   tool result; the model may insist. The memory sites narrow what enters the
   prompt. The judge and diagnosis only score.

3. **One ``decision`` trace record per call** (``agent/ops/tracing.py``):
   site, source (``jev`` / ``fallback``), the raw primitives Jev returned,
   the verdict derived, whether the harness acted, and — where the previous
   method is cheap enough to still run — what it would have decided, so
   agreement can be measured. A disabled decider (no key) emits nothing and
   every site is a no-op: the harness runs byte for byte as before.

What leaves the process as ``state`` is the user's message, a short
text-only view of the conversation (tool arguments included, tool outputs
truncated, images reduced to a marker) and — for the memory sites — the
retrieved rows. Never the full history, never image bytes
(docs/SECURITY.md §4).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from agent.decide.jev import (
    Choice,
    Decider,
    Decision,
    JevError,
    JSONContent,
    Noul,
    NoulCriteria,
    Question,
    Score,
    ScoreAnswer,
)
from agent.observability import Observer

Source = Literal["jev", "fallback", "disabled"]


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    confidence_threshold: float = 0.8
    """A ``choice``/``score`` answer below this confidence is "unsure" and the
    site falls back. Starting point from the first live probe (wrong answers
    sat at 0.42–0.72, right ones at or above 0.86); to be re-fit on the
    labelled set (``evals/jev``), never tuned by hand after an incident."""

    conversation_window: int = 8
    """Recent conversation entries that go into a review's ``state`` — enough
    to know what the user asked and what the assistant already did this
    turn, bounded so a long thread doesn't grow the state (or its cost)."""

    max_content_chars: int = 600
    """Per-entry truncation inside the conversation view: a tool output can
    be pages long; the reviewer needs the gist, not the payload."""

    judge_confidence_threshold: float = 0.85
    """Escalate a turn to the LLM judge when less than this share of the
    ``quality`` distribution sits within one level of the expected score.
    Jev's own ``confidence`` on a score is the top level's probability, which
    reads a 0.45/0.55 split between "good" and "excellent" as doubt — on the
    first live smoke that escalated 17 of 23 turns. Adjacent mass escalates
    only the bimodal cases (mass on 0 *and* on 3), 5 of those 23, and those
    were exactly the turns the LLM judge scored 0."""

    max_state_chars: int = 48_000
    """Hard cap on a free-text ``state`` (the consolidation log). Jev rejects
    a state above ~32k tokens with ``400 max_tokens_exceeded`` (measured:
    96k chars of Spanish chat log passed, 128k failed); a user with a long
    unconsolidated backlog must not turn the gate into a guaranteed
    fallback. The tail is kept — it is the most recent, and the question is
    "anything worth keeping", which a sample answers as well as the whole."""


# --- verdicts -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetrievalVerdict:
    retrieve: bool
    facts: bool
    episodes: bool
    p_needs_history: float
    source: Source


@dataclass(frozen=True, slots=True)
class MemorySelection:
    kept: list[str]
    dropped: int
    source: Source


@dataclass(frozen=True, slots=True)
class SkillVerdict:
    skills: list[str]
    """Skill names to load. At most one when Jev decided; the keyword
    matcher's picks when it did not."""
    confidence: float
    source: Source


@dataclass(frozen=True, slots=True)
class ToolReview:
    tool: str
    p_fits: float
    best_tool: str
    best_confidence: float
    risk: int
    """0 read-only · 1 modifies data · 2 moves money."""
    risk_confidence: float
    source: Source
    suggestion: str | None = None
    """Set when the harness should hand the model a second opinion before
    running the call. ``None`` → run it."""


@dataclass(frozen=True, slots=True)
class AskOrAct:
    action: Literal["ask", "act"]
    confidence: float
    source: Source
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class ConsolidationGate:
    proceed: bool
    p_worth_it: float
    source: Source


@dataclass(frozen=True, slots=True)
class FactSelection:
    kept: list[dict[str, Any]]
    dropped: int
    source: Source


@dataclass(frozen=True, slots=True)
class TurnJudgement:
    quality: float
    """0 harmful/wrong · 1 unhelpful · 2 partial · 3 good · 4 excellent."""
    quality_confidence: float
    """Share of the distribution within one level of ``quality`` (not Jev's
    top-level probability — see ``DecisionConfig.judge_confidence_threshold``)."""
    p_grounded: float
    p_resolved: float
    source: Source
    needs_llm_judge: bool
    """Jev was unsure about ``quality``: escalate this turn to the LLM judge."""


QUALITY_LEVELS: tuple[str, ...] = (
    "Wrong or harmful: states something false, promises an outcome it cannot "
    "deliver, or exposes data it shouldn't.",
    "Unhelpful: dodges the question, or asks for information already given.",
    "Partial: addresses the request but leaves an obvious gap or next step unclear.",
    "Good: correct, grounded in the tool results, and gives the user a clear "
    "next step.",
    "Excellent: good, plus concise and anticipates the natural follow-up.",
)
"""The judge's rubric; level ``i`` is the score ``i`` (0–4)."""

FAILURE_SITES: dict[str, str] = {
    "retrieval": "The reply ignored or misused the customer's history/profile.",
    "skill": "The reply did not follow the procedure for this situation.",
    "tool_choice": "The assistant called the wrong tool, or none when one fit.",
    "tool_data": "The tool returned an error or data that didn't answer the question.",
    "reply_wording": "Right facts, poor wording: unclear, too long, wrong tone.",
    "asked_instead_of_acting": "It asked the customer something it could resolve.",
    "out_of_scope": "The request needs a capability the assistant does not have.",
    "no_failure": "The reply looks correct; the rating is about something else.",
}


@dataclass(frozen=True, slots=True)
class Diagnosis:
    failure_site: str | None
    confidence: float
    p_actionable: float
    source: Source


@dataclass(frozen=True, slots=True)
class SkillProposalVerdict:
    approved: bool
    p_recurring: float
    p_duplicate: float
    p_safe: float
    source: Source


# --- state helpers ------------------------------------------------------------


def conversation_view(
    messages: Sequence[dict[str, Any]], window: int = 8, max_chars: int = 600
) -> list[dict[str, str]]:
    """A text-only, truncated view of the tail of the working memory, for a
    decision ``state``. Tool uses become ``[tool_use name {args}]``, tool
    results ``[tool_result ...]``, images ``[image]``. Entries can be the
    SDK's content blocks (pydantic models) or plain dicts — both appear in
    ``run_loop``'s message list."""
    view: list[dict[str, str]] = []
    for message in list(messages)[-window:]:
        role = str(message.get("role", "user"))
        content = message.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(_block_text(block) for block in content)
        else:
            text = str(content)
        text = " ".join(text.split())
        if len(text) > max_chars:
            text = text[: max_chars - 1] + "…"
        view.append({"role": role, "content": text})
    return view


def _block_text(block: Any) -> str:
    kind = _field(block, "type")
    if kind == "text":
        return str(_field(block, "text") or "")
    if kind == "tool_use":
        args = json.dumps(_field(block, "input"), default=str, ensure_ascii=False)
        return f"[tool_use {_field(block, 'name')} {args}]"
    if kind == "tool_result":
        content = _field(block, "content")
        if isinstance(content, list):
            content = " ".join(_block_text(b) for b in content)
        return f"[tool_result {content}]"
    if kind == "image":
        return "[image]"
    return ""


def _field(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _adjacent_mass(answer: ScoreAnswer) -> float:
    """Share of a score's distribution within one level of its expected
    value. "Good or excellent" is a confident answer on a 0–4 rubric;
    "wrong or good" is not. Jev's ``confidence`` (top level's probability)
    cannot tell the two apart; this can."""
    centre = round(answer.score)
    return sum(
        p for level, p in answer.probabilities.items() if abs(int(level) - centre) <= 1
    )


def _tool_catalog(tools: Sequence[tuple[str, str]]) -> dict[str, JSONContent | None]:
    return {name: description for name, description in tools}


# --- the facade ---------------------------------------------------------------


class Decisions:
    """The harness's judgment calls. Built once (``build_agent``) with the
    process-wide :class:`Decider`, or with ``None`` to disable every site."""

    def __init__(
        self, decider: Decider | None, config: DecisionConfig | None = None
    ) -> None:
        self._decider = decider
        self.config = config or DecisionConfig()

    @property
    def enabled(self) -> bool:
        return self._decider is not None

    def _confident(self, confidence: float) -> bool:
        return confidence >= self.config.confidence_threshold

    async def _ask(
        self,
        site: str,
        state: JSONContent,
        questions: dict[str, Question],
        notify: Observer | None,
        **context: Any,
    ) -> Decision | None:
        """One round-trip. ``None`` means "no verdict": the decider is off
        (nothing traced) or the call failed (a ``decision`` record with
        ``source="fallback"`` and the error). Callers take their fallback."""
        if self._decider is None:
            return None
        if isinstance(state, str) and len(state) > self.config.max_state_chars:
            state = (
                "[earlier exchanges omitted]\n" + state[-self.config.max_state_chars :]
            )
        try:
            return await self._decider.decide(state, questions)
        except JevError as exc:
            self._emit(
                notify,
                site,
                None,
                source="fallback",
                acted=False,
                error=str(exc),
                **context,
            )
            return None

    def _emit(
        self,
        notify: Observer | None,
        site: str,
        decision: Decision | None,
        *,
        source: Source,
        acted: bool,
        verdict: dict[str, Any] | None = None,
        baseline: dict[str, Any] | None = None,
        agreement: bool | None = None,
        error: str | None = None,
        **context: Any,
    ) -> None:
        if notify is None:
            return
        notify(
            "decision",
            {
                "site": site,
                "source": source,
                "model": decision.model if decision else None,
                "latency_ms": decision.latency_ms if decision else None,
                "usage": {
                    "in": decision.usage.input_tokens,
                    "out": decision.usage.output_tokens,
                }
                if decision
                else None,
                "threshold": self.config.confidence_threshold,
                "answers": decision.as_trace() if decision else {},
                "verdict": verdict or {},
                "acted": acted,
                "baseline": baseline,
                "agreement": agreement,
                "error": error,
                **context,
            },
        )

    # ---- J1 · retrieval gate -------------------------------------------------
    async def retrieval(
        self, message: str, notify: Observer | None = None
    ) -> RetrievalVerdict | None:
        """Does answering this message need the user's stored memory? The
        kind of memory is asked too, but only recorded. ``None`` when there
        is no verdict (caller runs the previous gate)."""
        questions: dict[str, Question] = {
            "needs_history": Noul(
                instructions=(
                    "A customer of a buy-now-pay-later company (or an employee of "
                    "a merchant that sells with it) writes to support. Does "
                    "answering this message WELL require the support system's "
                    "stored memory of THIS person: their profile, preferences, "
                    "past tickets and how they were resolved?"
                ),
                criteria=NoulCriteria(
                    true=(
                        "Refers to a prior contact ('again', 'still', 'last time'); "
                        "a problem whose cause may depend on their setup or a past "
                        "fix; a follow-up or complaint about how something was "
                        "handled; asks about their account, plan or an open request."
                    ),
                    false=(
                        "A greeting, thanks or pleasantry; a general how-to answerable "
                        "from documentation; a fully self-contained request where the "
                        "message holds every detail needed (e.g. an order number to "
                        "look up)."
                    ),
                ),
            ),
            "memory_kind": Choice(
                instructions="If memory were consulted, which kind would help most?",
                criteria={
                    "facts": "Durable facts: profile, preferences, plan, setup.",
                    "episodes": (
                        "Past conversations: what was reported and how it ended."
                    ),
                    "both": "Both kinds are plausibly relevant.",
                },
            ),
        }
        decision = await self._ask("retrieval", message, questions, notify)
        if decision is None:
            return None
        needs = decision.noul("needs_history")
        kind = decision.choice("memory_kind")
        retrieve = needs.yes
        # ``memory_kind`` is recorded, not acted on. Narrowing to one store
        # saved one cheap Postgres query and, in the live smoke, cost the
        # recall: a confident "episodes" skipped the facts that held the
        # answer. Both stores are searched (the pre-ADR behaviour) and
        # ``memory_select`` recovers precision row by row. ``would_narrow``
        # in the trace measures how often a confident kind disagrees.
        verdict = RetrievalVerdict(
            retrieve=retrieve,
            facts=retrieve,
            episodes=retrieve,
            p_needs_history=needs.noul,
            source="jev",
        )
        self._emit(
            notify,
            "retrieval",
            decision,
            source="jev",
            acted=True,
            verdict={
                "retrieve": retrieve,
                "kind": kind.choice,
                "would_narrow": retrieve
                and self._confident(kind.confidence)
                and kind.choice != "both",
            },
        )
        return verdict

    # ---- J4 · memory re-rank -------------------------------------------------
    async def memory_select(
        self, message: str, rows: list[str], notify: Observer | None = None
    ) -> MemorySelection:
        """Which of the retrieved rows actually belong in the prompt for this
        message. Everything stays when there is no verdict."""
        if not rows:
            return MemorySelection(kept=[], dropped=0, source="disabled")
        questions: dict[str, Question] = {
            f"row_{i}": Noul(
                instructions=(
                    f"Memory entry: {row}\n\nIs this entry relevant to answering "
                    "the customer's current message, such that leaving it out "
                    "would make the answer worse?"
                )
            )
            for i, row in enumerate(rows)
        }
        decision = await self._ask(
            "memory_select", {"message": message}, questions, notify
        )
        if decision is None:
            return MemorySelection(
                kept=list(rows),
                dropped=0,
                source="fallback" if self.enabled else "disabled",
            )
        kept = [row for i, row in enumerate(rows) if decision.noul(f"row_{i}").yes]
        self._emit(
            notify,
            "memory_select",
            decision,
            source="jev",
            acted=len(kept) != len(rows),
            verdict={"offered": len(rows), "kept": len(kept)},
        )
        return MemorySelection(kept=kept, dropped=len(rows) - len(kept), source="jev")

    # ---- J2 · skill match ----------------------------------------------------
    async def skill_match(
        self,
        message: str,
        skills: Sequence[tuple[str, str]],
        baseline: Sequence[str],
        notify: Observer | None = None,
    ) -> SkillVerdict:
        """Which skill policy (if any) applies to this message. ``baseline``
        is what the keyword matcher picked — the fallback, and the thing
        agreement is measured against."""
        if not skills:
            return SkillVerdict(skills=[], confidence=0.0, source="disabled")
        questions: dict[str, Question] = {
            "skill": Choice(
                instructions=(
                    "A support assistant has procedure notes ('skills'), each "
                    "described by when it should be used. Which ONE applies to the "
                    "customer's message? Pick 'none' when no note's description "
                    "fits — loading an unrelated procedure makes answers worse."
                ),
                criteria={
                    **_tool_catalog(skills),
                    "none": "No skill description fits this message.",
                },
            )
        }
        decision = await self._ask("skill_match", message, questions, notify)
        if decision is None:
            return SkillVerdict(
                skills=list(baseline),
                confidence=0.0,
                source="fallback" if self.enabled else "disabled",
            )
        answer = decision.choice("skill")
        confident = self._confident(answer.confidence)
        if confident:
            chosen = [] if answer.choice == "none" else [answer.choice]
        else:
            chosen = list(baseline)
        self._emit(
            notify,
            "skill_match",
            decision,
            source="jev",
            acted=confident,
            verdict={"skills": chosen, "confident": confident},
            baseline={"skills": list(baseline)},
            agreement=set(chosen) == set(baseline),
        )
        return SkillVerdict(skills=chosen, confidence=answer.confidence, source="jev")

    # ---- J3 · tool-call review -----------------------------------------------
    async def tool_review(
        self,
        conversation: Sequence[dict[str, Any]],
        call_name: str,
        call_args: dict[str, Any],
        visible_tools: Sequence[tuple[str, str]],
        notify: Observer | None = None,
    ) -> ToolReview | None:
        """Second opinion on one tool call the model wants to make. Returns a
        suggestion only for a confident misfit; the loop hands it to the
        model once and lets it insist."""
        state = {
            "conversation": conversation_view(
                conversation,
                self.config.conversation_window,
                self.config.max_content_chars,
            ),
            "proposed_call": {"tool": call_name, "arguments": call_args},
        }
        questions: dict[str, Question] = {
            "fits": Noul(
                instructions=(
                    "Given the conversation, is the proposed tool call the right "
                    "next step to help the user — the right tool, with arguments "
                    "that match what they asked?"
                ),
                criteria=NoulCriteria(
                    false=(
                        "A different tool answers the question better; the "
                        "arguments don't match the request; the information is "
                        "already in the conversation; or the call acts before the "
                        "user asked for that action."
                    )
                ),
            ),
            "best_tool": Choice(
                instructions=(
                    "Which of these would be the best next step for the user's "
                    "request right now?"
                ),
                criteria={
                    **_tool_catalog(visible_tools),
                    "reply": "No tool: answer the user directly from what is known.",
                },
            ),
            "risk": Score(
                instructions="How consequential is executing the proposed call?",
                criteria=[
                    "Read-only: it only looks something up.",
                    "Modifies data: creates, updates or cancels something.",
                    "Moves money or commits the company to an outcome.",
                ],
            ),
        }
        decision = await self._ask(
            "tool_review", state, questions, notify, tool=call_name
        )
        if decision is None:
            return None
        fits = decision.noul("fits")
        best = decision.choice("best_tool")
        risk = decision.score("risk")
        misfit = (
            not fits.yes
            and self._confident(best.confidence)
            and best.choice != call_name
        )
        suggestion = None
        if misfit:
            alternative = (
                "answering the user directly from what you already know"
                if best.choice == "reply"
                else f"`{best.choice}`"
            )
            suggestion = (
                f"Harness review: `{call_name}` with these arguments may not be "
                f"the right next step for what the user asked (fit "
                f"{fits.noul:.0%}); {alternative} looks like a better fit. "
                f"Reconsider — if you still think `{call_name}` is right, call "
                "it again and it will run."
            )
        self._emit(
            notify,
            "tool_review",
            decision,
            source="jev",
            acted=suggestion is not None,
            verdict={
                "fits": fits.yes,
                "best_tool": best.choice,
                "misfit": misfit,
                "risk": int(round(risk.score)),
            },
            tool=call_name,
        )
        return ToolReview(
            tool=call_name,
            p_fits=fits.noul,
            best_tool=best.choice,
            best_confidence=best.confidence,
            risk=int(round(risk.score)),
            risk_confidence=risk.confidence,
            source="jev",
            suggestion=suggestion,
        )

    # ---- J7 · ask or act -----------------------------------------------------
    async def ask_or_act(
        self,
        conversation: Sequence[dict[str, Any]],
        prompt: str,
        options: Sequence[dict[str, Any]],
        visible_tools: Sequence[tuple[str, str]],
        notify: Observer | None = None,
    ) -> AskOrAct | None:
        """The model wants to pause and ask the user to choose. Should it,
        or can it move the request forward on its own? A confident ``act``
        becomes a suggestion the loop hands back once."""
        state = {
            "conversation": conversation_view(
                conversation,
                self.config.conversation_window,
                self.config.max_content_chars,
            ),
            "proposed_question": {
                "prompt": prompt,
                "options": [str(o.get("label", o)) for o in options],
            },
            "tools_available": [name for name, _ in visible_tools],
        }
        questions: dict[str, Question] = {
            "action": Choice(
                instructions=(
                    "The assistant wants to pause the conversation and ask the "
                    "user the proposed question. Should it ask now, or act?"
                ),
                criteria={
                    "ask": (
                        "Only the user can answer: a genuine fork between options "
                        "with different outcomes, or information no tool can "
                        "provide."
                    ),
                    "act": (
                        "The request can be resolved or moved forward with an "
                        "available tool or from what is already known; asking "
                        "only delays the user."
                    ),
                },
            )
        }
        decision = await self._ask("ask_or_act", state, questions, notify)
        if decision is None:
            return None
        answer = decision.choice("action")
        act = answer.choice == "act" and self._confident(answer.confidence)
        suggestion = None
        if act:
            suggestion = (
                "Harness review: the user's request looks answerable without "
                f"asking them to choose (confidence {answer.confidence:.0%}). Try "
                "to resolve it with your tools or from what you already know. "
                "If you still need their choice, call present_choice again and "
                "it will be shown."
            )
        self._emit(
            notify,
            "ask_or_act",
            decision,
            source="jev",
            acted=act,
            verdict={"action": answer.choice, "nudged": act},
        )
        return AskOrAct(
            action="act" if answer.choice == "act" else "ask",
            confidence=answer.confidence,
            source="jev",
            suggestion=suggestion,
        )

    # ---- A · consolidation gate ---------------------------------------------
    async def consolidation_gate(
        self, log: str, notify: Observer | None = None
    ) -> ConsolidationGate:
        """Before paying for a summarizer call: is there anything in these
        exchanges worth distilling into long-term memory? Biased to proceed
        (skips only below 0.3) — a lost memory costs more than a wasted call."""
        questions: dict[str, Question] = {
            "worth_it": Noul(
                instructions=(
                    "Below are recent support exchanges with one customer. Do they "
                    "contain anything worth keeping in long-term memory about this "
                    "customer: a durable fact about them, their setup or "
                    "preferences, or a notable event (a problem reported, how it "
                    "was resolved) worth recalling in a month?"
                ),
                criteria=NoulCriteria(
                    false=(
                        "Only greetings, tests, generic how-to questions with no "
                        "personal detail, or chit-chat."
                    )
                ),
            )
        }
        decision = await self._ask("consolidation_gate", log, questions, notify)
        if decision is None:
            return ConsolidationGate(
                proceed=True,
                p_worth_it=1.0,
                source="fallback" if self.enabled else "disabled",
            )
        p = decision.noul("worth_it").noul
        proceed = p >= 0.3
        self._emit(
            notify,
            "consolidation_gate",
            decision,
            source="jev",
            acted=not proceed,
            verdict={"proceed": proceed},
        )
        return ConsolidationGate(proceed=proceed, p_worth_it=p, source="jev")

    # ---- J8 · fact selection --------------------------------------------------
    async def fact_select(
        self,
        facts: list[dict[str, Any]],
        existing: Sequence[str],
        notify: Observer | None = None,
    ) -> FactSelection:
        """Which of the summarizer's candidate facts deserve to be stored:
        durable, specific, and not already known."""
        if not facts:
            return FactSelection(kept=[], dropped=0, source="disabled")
        state = {
            "candidate_facts": [
                {"subject": f.get("subject"), "content": f.get("content")}
                for f in facts
            ],
            "already_stored": list(existing),
        }
        questions: dict[str, Question] = {
            f"fact_{i}": Noul(
                instructions=(
                    f"Candidate fact #{i}: [{f.get('subject')}] {f.get('content')}\n\n"
                    "Is this a durable, specific fact about the customer worth "
                    "remembering in a month — and NOT already captured by one of "
                    "the facts already stored?"
                )
            )
            for i, f in enumerate(facts)
        }
        decision = await self._ask("fact_select", state, questions, notify)
        if decision is None:
            return FactSelection(
                kept=list(facts),
                dropped=0,
                source="fallback" if self.enabled else "disabled",
            )
        kept = [f for i, f in enumerate(facts) if decision.noul(f"fact_{i}").yes]
        self._emit(
            notify,
            "fact_select",
            decision,
            source="jev",
            acted=len(kept) != len(facts),
            verdict={"offered": len(facts), "kept": len(kept)},
        )
        return FactSelection(kept=kept, dropped=len(facts) - len(kept), source="jev")

    # ---- E · judge --------------------------------------------------------------
    async def judge_turn(
        self,
        user_message: str,
        reply: str,
        tools_used: Sequence[dict[str, Any]],
        skills: Sequence[str],
        audience: str,
        notify: Observer | None = None,
    ) -> TurnJudgement | None:
        """Score one finished turn. ``None`` when there is no verdict."""
        state = {
            "audience": audience,
            "user_message": user_message,
            "tools_used": [
                {
                    "tool": t.get("tool"),
                    "args": t.get("args"),
                    "output": str(t.get("output", ""))[: self.config.max_content_chars],
                }
                for t in tools_used
            ],
            "skills_loaded": list(skills),
            "assistant_reply": reply,
        }
        questions: dict[str, Question] = {
            "quality": Score(
                instructions=(
                    "Rate the assistant's reply to this support message. The "
                    "assistant may only read data through its tools; it cannot "
                    "cancel, refund or approve anything itself."
                ),
                criteria=list(QUALITY_LEVELS),
            ),
            "grounded": Noul(
                instructions=(
                    "Is every factual claim in the reply (statuses, amounts, "
                    "dates, what the user can do) supported by the tool outputs "
                    "or by the user's own message? Reply 'no' if it asserts "
                    "something no tool returned."
                )
            ),
            "resolved": Noul(
                instructions=(
                    "Did the user get what they asked for in this reply? Judge "
                    "the whole reply, not its opening line."
                ),
                criteria=NoulCriteria(
                    true=(
                        "The requested status, amount, date, list or answer is in "
                        "the reply (it may also narrate the lookup it did); or the "
                        "user asked for nothing concrete (a greeting) and the "
                        "reply answers in kind; or the request cannot be done and "
                        "the reply says exactly where or how it can be."
                    ),
                    false=(
                        "The reply stops at asking the user for more information "
                        "(an order number, details of the problem), says the data "
                        "is unavailable right now, only announces what it will do "
                        "without the result, or hands off to a human without an "
                        "outcome."
                    ),
                ),
            ),
        }
        decision = await self._ask("judge", state, questions, notify)
        if decision is None:
            return None
        quality = decision.score("quality")
        grounded = decision.noul("grounded")
        resolved = decision.noul("resolved")
        quality_confidence = _adjacent_mass(quality)
        needs_llm = quality_confidence < self.config.judge_confidence_threshold
        self._emit(
            notify,
            "judge",
            decision,
            source="jev",
            acted=needs_llm,
            verdict={
                "quality": round(quality.score, 2),
                "quality_confidence": round(quality_confidence, 2),
                "grounded": grounded.yes,
                "resolved": resolved.yes,
                "needs_llm_judge": needs_llm,
            },
        )
        return TurnJudgement(
            quality=quality.score,
            quality_confidence=quality_confidence,
            p_grounded=grounded.noul,
            p_resolved=resolved.noul,
            source="jev",
            needs_llm_judge=needs_llm,
        )

    # ---- F · diagnose -----------------------------------------------------------
    async def diagnose(
        self,
        user_message: str,
        reply: str,
        tools_used: Sequence[dict[str, Any]],
        skills: Sequence[str],
        comment: str | None,
        notify: Observer | None = None,
    ) -> Diagnosis | None:
        """A user rated a reply down: where in the harness did it most
        likely go wrong? A confident label is a triage hint, not a verdict."""
        state = {
            "user_message": user_message,
            "tools_used": [
                {"tool": t.get("tool"), "status": t.get("status")} for t in tools_used
            ],
            "skills_loaded": list(skills),
            "assistant_reply": reply,
            "user_comment": comment or "",
        }
        questions: dict[str, Question] = {
            "failure_site": Choice(
                instructions=(
                    "The user rated this reply thumbs-down. Which part of the "
                    "support system most likely caused the bad reply?"
                ),
                criteria=dict(FAILURE_SITES),
            ),
            "actionable": Noul(
                instructions=(
                    "Could an engineer act on this case (fix a prompt, a tool, a "
                    "procedure note) — as opposed to the user being upset about "
                    "something outside the assistant's control?"
                )
            ),
        }
        decision = await self._ask("diagnose", state, questions, notify)
        if decision is None:
            return None
        site = decision.choice("failure_site")
        actionable = decision.noul("actionable")
        confident = self._confident(site.confidence)
        self._emit(
            notify,
            "diagnose",
            decision,
            source="jev",
            acted=confident,
            verdict={
                "failure_site": site.choice if confident else None,
                "candidate": site.choice,
                "actionable": actionable.yes,
            },
        )
        return Diagnosis(
            failure_site=site.choice if confident else None,
            confidence=site.confidence,
            p_actionable=actionable.noul,
            source="jev",
        )

    # ---- B · skill proposal gate ---------------------------------------------
    async def review_skill_proposal(
        self,
        name: str,
        description: str,
        body: str,
        existing: Sequence[tuple[str, str]],
        conversation: Sequence[dict[str, Any]],
        notify: Observer | None = None,
    ) -> SkillProposalVerdict:
        """Gatekeeper for a skill the model wants to write for itself. All
        three must hold: the situation recurs, no existing skill covers it,
        and the policy is safe. Without a verdict nothing is approved."""
        state = {
            "proposal": {"name": name, "description": description, "body": body},
            "existing_skills": [{"name": n, "description": d} for n, d in existing],
            "conversation": conversation_view(
                conversation,
                self.config.conversation_window,
                self.config.max_content_chars,
            ),
        }
        questions: dict[str, Question] = {
            "recurring": Noul(
                instructions=(
                    "Does the conversation show a situation that will plausibly "
                    "recur for other users and that the assistant handled poorly "
                    "or with effort for lack of a procedure note?"
                )
            ),
            "duplicate": Noul(
                instructions=(
                    "Is the proposed skill already covered — same situation, "
                    "same guidance — by one of the existing skills?"
                )
            ),
            "safe": Noul(
                instructions=(
                    "Is the proposed procedure safe to give the assistant: no "
                    "instruction to move money, cancel, refund or approve "
                    "anything, no promise of outcomes, nothing that contradicts "
                    "'only read data, never invent facts'?"
                )
            ),
        }
        decision = await self._ask("skill_proposal", state, questions, notify)
        if decision is None:
            return SkillProposalVerdict(
                approved=False,
                p_recurring=0.0,
                p_duplicate=1.0,
                p_safe=0.0,
                source="fallback" if self.enabled else "disabled",
            )
        recurring = decision.noul("recurring")
        duplicate = decision.noul("duplicate")
        safe = decision.noul("safe")
        approved = recurring.yes and not duplicate.yes and safe.yes
        self._emit(
            notify,
            "skill_proposal",
            decision,
            source="jev",
            acted=approved,
            verdict={"approved": approved, "name": name},
        )
        return SkillProposalVerdict(
            approved=approved,
            p_recurring=recurring.noul,
            p_duplicate=duplicate.noul,
            p_safe=safe.noul,
            source="jev",
        )


async def review_batch(
    decisions: Decisions,
    conversation: Sequence[dict[str, Any]],
    calls: Sequence[tuple[str, dict[str, Any]]],
    visible_tools: Sequence[tuple[str, str]],
    notify: Observer | None = None,
) -> list[ToolReview | None]:
    """Review every call of a batch concurrently — one round-trip of latency
    for the whole batch, the same way the loop executes the batch itself."""
    return list(
        await asyncio.gather(
            *(
                decisions.tool_review(conversation, name, args, visible_tools, notify)
                for name, args in calls
            )
        )
    )


__all__ = [
    "FAILURE_SITES",
    "QUALITY_LEVELS",
    "AskOrAct",
    "ConsolidationGate",
    "DecisionConfig",
    "Decisions",
    "Diagnosis",
    "FactSelection",
    "MemorySelection",
    "RetrievalVerdict",
    "SkillProposalVerdict",
    "SkillVerdict",
    "Source",
    "ToolReview",
    "TurnJudgement",
    "conversation_view",
    "review_batch",
]
