"""ToolContext — the per-call envelope ``ToolRegistry.execute`` threads into
identity-gated tools.

An envelope instead of bare kwargs so each per-call concern (identity, which
conversation this is) is an additive field, not a calling-convention change
across every tool and ``ToolRegistry.execute``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from agent.identity import Principal


@dataclass(frozen=True, slots=True)
class ToolContext:
    principal: Principal | None = None
    # Which conversation this tool call belongs to — set by Agent.respond()
    # for every real turn (None only in tests that build a bare ToolContext).
    # Used by escalate_to_human (agent/tools/implementations/escalation.py)
    # to mark the right chat_sessions row; not identity-gated, since an
    # anonymous visitor can still need a human ("I can't log in at all").
    session_id: uuid.UUID | None = None
