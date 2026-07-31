"""ToolContext — the per-call envelope ``ToolRegistry.execute`` threads into
identity-gated tools.

One field today (``principal``); an envelope instead of a bare ``user_id``
kwarg so a second per-call concern later (a request id, eventually an
Intercom client) is an additive field, not a calling-convention change across
every identity tool and ``ToolRegistry.execute``.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.identity import Principal


@dataclass(frozen=True, slots=True)
class ToolContext:
    principal: Principal | None = None
