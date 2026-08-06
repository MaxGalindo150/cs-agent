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

from agent.identity import Principal
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
- Never promise an action you can't verify or resolve yourself (a refund, a
  manual account fix, anything outside what you can do here) — call
  escalate_to_human and tell the customer, in plain terms, that you can't
  handle that one yourself and a person will follow up. Never mention tools,
  systems, or your own limitations mechanically — just say plainly you can't
  help with that specific thing.
- You can see images the customer attaches — describe or reference what's in
  them freely, that's not "inventing" anything. But an image alone never
  proves a fact you'd normally verify with a tool (a payment, an order
  status) — if what you see needs verifying before you act on it, say so and
  check with a tool, don't just take the image's word for it.

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

    def __init__(
        self, session_id: uuid.UUID, memory: Any = None, soul: str = ""
    ) -> None:
        # session_id is a real chat_sessions PK (created up front), not Waku's
        # free-string tag — chat_messages FKs to it. Required and first: a UUID
        # has no literal default, and a required arg can't follow `memory=None`.
        self.session_id = session_id
        self.memory = memory  # agent.memory.Memory (None until it's wired)
        self.history: list[dict[str, Any]] = []
        # The persona this session runs with — passed by the Agent so different
        # profiles (buyer vs merchant) can coexist without load_soul being
        # profile-aware. Empty default falls back to the buyer soul (backward
        # compat for tests that build a bare Session).
        self._soul = soul or DEFAULT_SOUL

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
        user_id: str | None = None,
        notify: Observer | None = None,
        principal: Principal | None = None,
    ) -> str:
        # The service should know the request-handling clock so the model can
        # resolve relative dates ("ayer", "en 30 minutos"). TODO: timezone via env.
        now = datetime.now().astimezone()
        parts = [
            self._soul,
            f"\nRight now it is {now:%A, %Y-%m-%d %H:%M} ({now:%Z}, UTC{now:%z}).",
        ]

        # Tell the model whether the host app already identified the caller,
        # without injecting raw header values into the system prompt. ToolContext
        # carries the actual ids; the model only needs to know it should use the
        # scoped tools instead of asking the caller to identify themselves again.
        if principal is None:
            parts.append(
                "\nCurrent caller context (provided by the host application):\n"
                "- No caller is identified. Identity-scoped tools are unavailable.\n"
                "- For account-specific requests, do not ask for account identifiers "
                "and do not offer a lookup. Tell the caller to identify themselves "
                "through the host application first. You may still answer general "
                "questions."
            )
        else:
            if principal.profile == "merchant":
                employee_context = (
                    "An employee is also identified for employee-specific actions."
                    if principal.employee_id
                    else (
                        "No employee is identified; ask for one only when the task "
                        "requires it."
                    )
                )
                parts.append(
                    "\nCurrent caller context (provided by the host application):\n"
                    "- A merchant is already identified. Do not ask for their RIF or "
                    "business name merely to identify them.\n"
                    "- Merchant-scoped tools receive the merchant identity from the "
                    "harness. Never ask for or pass a merchant_id in tool calls.\n"
                    f"- {employee_context}"
                )
            else:
                parts.append(
                    "\nCurrent caller context (provided by the host application):\n"
                    "- A customer is already identified. Identity-scoped tools receive "
                    "that identity from the harness; do not ask for their user id."
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
