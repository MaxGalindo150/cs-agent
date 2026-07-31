"""Working-memory assembly — the system prompt Cheo runs with, per turn.

The "inner box": rebuilt each turn, thrown away. What persists lives in
agent/memory. Working memory =

    SOUL (identity + how it works)     ← who Cheo is
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
from datetime import datetime
from typing import Any

from agent.observability import LoopEvent, Observer

DEFAULT_SOUL = """\
You are Cheo, a customer-support agent for Cashea, a Buy-Now-Pay-Later service.
You are concise, warm, and proactive.

How you work:
- Ground every answer in your tools. Never invent order, payment, shipment, or
  account details — look them up. If you're missing an id or the data isn't
  there, say so plainly or ask the customer for what you need (e.g. the order id).
- Relay tool results honestly: state what you actually found or did, never a
  status, amount, or action the tool output doesn't support.

Your tools' descriptions say what each one does and when to use it. Detailed
procedures for specific situations arrive as skill instructions when they apply.
"""


def load_soul() -> str:
    """The persona. Waku reads an editable SOUL.md from the user's home dir
    (procedural memory you can hand-edit); serverless has no durable local disk,
    so for now the soul is this constant. A config- or DB-backed editable soul
    is a later decision."""
    return DEFAULT_SOUL


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

    async def build_system(
        self, user_message: str, notify: Observer | None = None
    ) -> str:
        # The service should know the request-handling clock so the model can
        # resolve relative dates ("ayer", "en 30 minutos"). TODO: timezone via env.
        now = datetime.now().astimezone()
        parts = [
            load_soul(),
            f"\nRight now it is {now:%A, %Y-%m-%d %H:%M} ({now:%Z}, UTC{now:%z}).",
        ]

        if self.memory is not None:
            # Hero moment #1: a cheap judge decides IF we retrieve at all —
            # default-on retrieval is slow and biases answers (see
            # memory/retrieval_gate.py). Async here because the gate calls the LLM.
            retrieved = await self.memory.gated_retrieve(user_message, notify=notify)
            if retrieved:
                parts.append("\nRelevant memory:\n" + retrieved)
            skills = self.memory.matching_skills(user_message)
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
