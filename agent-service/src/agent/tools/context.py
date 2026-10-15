"""ToolContext — the per-call envelope ``ToolRegistry.execute`` threads into
identity-gated tools.

An envelope instead of bare kwargs so each per-call concern (identity, which
conversation this is) is an additive field, not a calling-convention change
across every tool and ``ToolRegistry.execute``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from agent.identity import Principal
from agent.observability import Observer


@dataclass(frozen=True, slots=True)
class ToolContext:
    principal: Principal | None = None
    # Which conversation this tool call belongs to — set by Agent.respond()
    # for every real turn (None only in tests that build a bare ToolContext).
    # Used by escalate_to_human (agent/tools/implementations/escalation.py)
    # to mark the right chat_sessions row; not identity-gated, since an
    # anonymous visitor can still need a human ("I can't log in at all").
    session_id: uuid.UUID | None = None
    # The aliado's own host-app credential (their Firebase ID token), for tools
    # that read Cashea's merchant API as them — the backend then applies the
    # aliado's own permissions. Set only for a verified aliado's chat turn
    # (service/core/host_credential.py); lives for this turn, in memory only.
    # repr=False so no log line, traceback or debugger dump ever prints it;
    # tools must never echo it back in their output (which is traced).
    host_credential: str | None = field(default=None, repr=False)
    # The turn's observer, for the rare tool that itself makes a harness
    # judgment call and must trace it (propose_skill). Set by Agent.respond()
    # alongside session_id; None in tests that build a bare ToolContext.
    notify: Observer | None = field(default=None, repr=False, compare=False)
