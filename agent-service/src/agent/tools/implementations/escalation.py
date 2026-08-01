"""Escalation — flagging a conversation for a human agent to review.

`needs_human` is a first-class result (CLAUDE.md §2), not something the model
free-talks its way through: this tool is the only way a session gets flagged,
and the flag is a deterministic DB write, not a promise the model makes on
its own. `agent/runtime/session.py::Session.fixed_response` reads it back on
every later turn and short-circuits the LLM entirely once set — the model
never gets a second chance to promise an outcome ("I'll get you refunded")
that no tool here can actually back.

``needs_context=True``, not ``requires_identity=True``: escalation must keep
working for an anonymous visitor too (e.g. "I can't log in at all") — the
session id alone is enough for a human to pull up the transcript.
"""

from __future__ import annotations

from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from agent.tools.context import ToolContext
from agent.tools.registry import Tool


def make_escalate_to_human_tool(db: Database) -> Tool:
    async def escalate_to_human(ctx: ToolContext, reason: str = "") -> str:
        assert ctx.session_id is not None  # every real turn has one
        if not reason:
            return (
                "escalate_to_human needs a reason — briefly say what a human "
                "needs to handle (e.g. 'duplicate payment charged, refund needed')."
            )
        async with db.session() as session:
            escalated_now = await SessionRepository(session).mark_escalated(
                ctx.session_id, reason
            )
        if not escalated_now:
            return "This conversation was already flagged for a human agent."
        return (
            "Flagged this conversation for a human agent to review. Tell the "
            "customer a person will follow up — do not promise a specific "
            "outcome, timeline, or refund amount yourself."
        )

    return Tool(
        name="escalate_to_human",
        progress_label="Escalating to a human agent",
        description=(
            "Flag this conversation for a human agent to take over — use this "
            "when the customer needs an action you have no tool for (a refund, "
            "a manual account fix, anything you can't verify or resolve "
            "yourself). After calling this, tell the customer a human will "
            "follow up; never promise what that person will do or when."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Brief summary of what the human needs to handle, e.g. "
                        "'duplicate payment charged on order ord_0001, refund needed'."
                    ),
                }
            },
            "required": ["reason"],
        },
        fn=escalate_to_human,
        needs_context=True,
    )
