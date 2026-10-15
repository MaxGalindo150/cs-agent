"""propose_skill — the agent drafts a SKILL.md for itself; the harness decides.

The whiteboard's "agent creates its own SKILL.md", built narrow on purpose
(ADR-0004 B, behind ``SKILL_PROPOSALS_ENABLED``, off by default):

- The model proposes ``name`` / ``description`` / ``body`` in the official
  skill format. The draft is validated like any SKILL.md
  (``procedural.loader._parse_text``).
- The decision model gates it on three yes/no questions — does the situation
  recur, is it already covered by an existing skill, is the policy safe —
  with the conversation and the audience's skill catalogue as context.
- The verdict and the full draft are **traced** (``skill_proposal`` event)
  and nothing else happens: the skill is never loaded into a prompt and
  never written anywhere. Cloud Run has no disk to write to, and an
  agent-authored policy must be read by a person before it steers the
  agent. A later step (its own ADR) stores approved proposals in Postgres
  with a review queue; this trace is the inbox until then.

The model is told exactly that, so it never expects the skill to take
effect in the same conversation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.decide.sites import Decisions
from agent.identity import audience_of
from agent.memory import Memory
from agent.memory.procedural.loader import _parse_text
from agent.tools.context import ToolContext
from agent.tools.registry import Tool

_MAX_BODY_LINES = 60
_HISTORY_TURNS = 6


def make_propose_skill_tool(memory: Memory, decisions: Decisions) -> Tool:
    async def propose_skill(
        ctx: ToolContext, name: str = "", description: str = "", body: str = ""
    ) -> str:
        name = name.strip().lower().replace(" ", "-")
        description = " ".join(description.split())
        body = body.strip()
        if not name or not description or not body:
            return "propose_skill needs a name, a description and a body."
        if len(body.splitlines()) > _MAX_BODY_LINES:
            return (
                f"The body is too long ({len(body.splitlines())} lines); skills "
                f"are at most {_MAX_BODY_LINES} human-readable lines."
            )
        draft = f"---\nname: {name}\ndescription: {description}\n---\n{body}\n"
        if _parse_text(draft, Path(f"<proposal:{name}>")) is None:
            return "The proposal is not a valid SKILL.md (name/description/body)."

        audience = audience_of(ctx.principal)
        existing = memory.skill_catalog(audience)
        if any(n == name for n, _ in existing):
            return f"A skill named '{name}' already exists for this audience."

        conversation: list[dict[str, Any]] = []
        if ctx.session_id is not None:
            recent = (await memory.session_history(ctx.session_id))[-_HISTORY_TURNS:]
            for user_text, reply in recent:
                conversation.append({"role": "user", "content": user_text})
                conversation.append({"role": "assistant", "content": reply})

        verdict = await decisions.review_skill_proposal(
            name, description, body, existing, conversation, ctx.notify
        )
        if ctx.notify is not None:
            ctx.notify(
                "skill_proposal",
                {
                    "audience": audience,
                    "name": name,
                    "description": description,
                    "body": body,
                    "approved": verdict.approved,
                    "p_recurring": round(verdict.p_recurring, 3),
                    "p_duplicate": round(verdict.p_duplicate, 3),
                    "p_safe": round(verdict.p_safe, 3),
                    "source": verdict.source,
                },
            )
        if verdict.source != "jev":
            return (
                "Recorded the proposal for human review. It could not be "
                "pre-screened right now; it will not take effect in this "
                "conversation."
            )
        if not verdict.approved:
            reasons = []
            if verdict.p_recurring < 0.5:
                reasons.append("the situation doesn't look like it recurs")
            if verdict.p_duplicate >= 0.5:
                reasons.append("an existing skill already covers it")
            if verdict.p_safe < 0.5:
                reasons.append("the policy isn't safe to hand the assistant")
            return (
                "Recorded the proposal, but it was not approved for review: "
                + "; ".join(reasons)
                + ". Continue helping the user without it."
            )
        return (
            "Recorded the proposal and flagged it for human review. It does "
            "not take effect in this conversation — continue helping the user "
            "with what you have."
        )

    return Tool(
        name="propose_skill",
        description=(
            "Propose a new procedure note (skill) for situations like this "
            "one, when you handled a recurring kind of request without a "
            "procedure and a short note would have helped. Give a short "
            "kebab-case name, a one-sentence description of WHEN to use it, "
            "and the procedure as at most 60 lines of Markdown. The proposal "
            "is reviewed by a person later; it never takes effect in this "
            "conversation, so keep helping the user without it."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "kebab-case skill name"},
                "description": {
                    "type": "string",
                    "description": "One sentence: when this skill applies.",
                },
                "body": {
                    "type": "string",
                    "description": "The procedure, Markdown, at most 60 lines.",
                },
            },
            "required": ["name", "description", "body"],
        },
        fn=propose_skill,
        needs_context=True,
        progress_label="Drafting a procedure note",
        silent=True,
    )
