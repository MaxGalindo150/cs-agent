"""Working-memory assembly — the system prompt Cheo runs with, per turn.

The "inner box": rebuilt each turn, thrown away. What persists lives in
agent/memory. Working memory =

    SOUL (identity + how it works)     ← who Cheo is, per audience
  + who the caller is                  ← an aliado's store and role
  + current time                       ← resolve relative dates
  + durable facts & episodes           ← what Cheo remembers (gated!)
  + matched skill instructions         ← domain policy, only when it applies
  + conversation history               ← this conversation
  + the user's new message             ← passed by the caller

The endpoint calls `build_system()` and never hardcodes the prompt. Memory is
optional: with no `memory` wired, a Session is just the SOUL + clock.
"""

from __future__ import annotations

import uuid
from typing import Any

from agent import clock
from agent.identity import AUDIENCES, Audience, Principal, audience_of
from agent.observability import LoopEvent, Observer
from agent.prompts import load_prompt

# One soul per audience (agent.identity.audience_of): end customers and
# aliados get different personas, scope and rules. Edited in prompts/souls/.
SOULS: dict[Audience, str] = {
    audience: load_prompt(f"souls/{audience}") for audience in AUDIENCES
}
DEFAULT_SOUL = SOULS["consumer"]


def load_soul(audience: Audience = "consumer") -> str:
    """The persona for this audience. Waku reads an editable SOUL.md from the
    user's home dir; serverless has no durable local disk, so souls ship with
    the code (prompts/souls/)."""
    return SOULS[audience]


def caller_context(principal: Principal | None) -> str | None:
    """Who an aliado is, from their verified merchant record — appended by
    code so the soul stays static text. None for anyone else."""
    if principal is None or audience_of(principal) != "merchant":
        return None
    store = principal.store_name or "their store"
    merchant = f" ({principal.merchant_name})" if principal.merchant_name else ""
    role = principal.role or "employee"
    return f'\nYou are talking to the {role} of the store "{store}"{merchant}.'


class Session:
    """Holds one conversation: the chat history plus the recipe for the system
    prompt. One Session per gateway connection."""

    def __init__(self, session_id: uuid.UUID, memory: Any = None) -> None:
        # session_id is a real chat_sessions PK (created up front), not Waku's
        # free-string tag — chat_messages FKs to it. Required and first: a UUID
        # has no literal default, and a required arg can't follow `memory=None`.
        self.session_id = session_id
        self.memory = memory  # agent.memory.Memory (None until it's wired)
        self.history: list[dict[str, Any]] = []

    async def fixed_response(self, user_message: str) -> str | None:
        """A canned reply that must bypass the LLM entirely, or ``None`` if
        this turn should run normally.

        Each check here is a deterministic harness guarantee, not something
        the model re-decides every turn — once a session is escalated, the
        model must never get another chance to promise something it can't
        back (this is what prompted the check: an agent that had already
        escalated a duplicate charge kept offering to "process the refund"
        on the next message). Sequential checks, not a plugin registry — a
        future case (e.g. a bare greeting) is just another early return
        added here, not a redesign.
        """
        if self.memory is not None and await self.memory.is_escalated(self.session_id):
            return (
                "This conversation was already flagged for a human agent, "
                "who will follow up shortly — no need to escalate it again."
            )
        return None

    async def build_system(
        self,
        user_message: str,
        principal: Principal | None = None,
        notify: Observer | None = None,
    ) -> str:
        audience = audience_of(principal)
        user_id = principal.user_id if principal else None
        # Venezuelan time, so the model resolves relative dates ("ayer", "en
        # 30 minutos") the way the user means them.
        now = clock.now()
        parts = [load_soul(audience)]
        context = caller_context(principal)
        if context:
            parts.append(context)
        parts.append(
            f"\nRight now it is {now:%A, %Y-%m-%d %H:%M} ({now:%Z}, UTC{now:%z})."
        )

        if self.memory is not None:
            # Hero moment #1: a cheap judge decides IF we retrieve at all —
            # default-on retrieval is slow and biases answers (see
            # memory/retrieval_gate.py). Async here because the gate calls the LLM.
            retrieved = await self.memory.gated_retrieve(
                user_message, user_id, notify=notify
            )
            if retrieved:
                parts.append("\nRelevant memory:\n" + retrieved)
            skills = self.memory.matching_skills(user_message, audience)
            if skills:
                parts.append("\nRelevant skill instructions:\n" + skills)

        return "\n".join(parts)

    async def add_exchange(
        self,
        user_message: str,
        reply: str,
        tool_calls: list[LoopEvent] | None = None,
        source: str = "api",
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Record the turn in history (working memory) and, if memory is wired,
        in the chat log (so consolidation can distil it later).

        Tool activity is folded into the assistant's history entry as a compact
        [tools used: ...] line. Without it, the model forgets it already acted
        and happily re-runs the same tool with the same parameters next turn.

        Async because ``log_chat`` writes to Postgres. ``source`` defaults to
        "api" — the transport should pass the real channel (whatsapp/webchat).
        """
        record = reply
        if tool_calls:
            summary = "; ".join(
                f"{c['tool']}({c['args']}) -> {c['output']}" for c in tool_calls
            )
            record = f"{reply}\n[tools used: {summary}]"
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": record})
        if self.memory is not None:
            await self.memory.log_chat(
                user_message,
                record,
                session_id=self.session_id,
                source=source,
                meta=meta,
            )

    # ---- session lifecycle (the "New chat" / history feature)
    # A session is just a tag on chat_log rows. Starting a new one clears working
    # memory; switching reloads a past conversation's history so replies have
    # context. Consolidation still reads ALL unconsolidated rows regardless.
    def start_new(self, session_id: uuid.UUID) -> None:
        self.session_id = session_id
        self.history = []

    async def switch(self, session_id: uuid.UUID, history_turns: int) -> None:
        self.session_id = session_id
        self.history = []
        if self.memory is None:
            return
        # Only the recent tail of a past conversation goes back into working
        # memory — don't hold the whole thread. Async because session_history
        # reads Postgres; windowed by HISTORY_TURNS (Waku uses settings).
        recent = (await self.memory.session_history(session_id))[-history_turns:]
        for user_msg, reply in recent:
            self.history.append({"role": "user", "content": user_msg})
            self.history.append({"role": "assistant", "content": reply})
