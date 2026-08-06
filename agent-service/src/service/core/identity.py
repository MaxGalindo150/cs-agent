"""Identity seam: where a verified end-user arrives from the transport.

STUB — trusts the identity headers verbatim, no verification happens here.
Neither this service nor the frontend has real auth yet (a deliberate, temporary
relaxation of "treat every inbound message as untrusted" — CLAUDE.md's
engineering bar), so this only runs in dev (``settings.is_development``);
everywhere else it returns ``None`` rather than let an unverified header
silently become staging/prod's auth.

*Which* headers carry the identity is profile knowledge, so each profile owns
that mapping (``agent/profiles/``) and this seam owns the trust decision. When
real auth lands, only the check below changes (verify a bearer JWT, extract its
subject claim instead of trusting a header) — the shape
(``-> Principal | None``) stays the same, so no route or agent-layer code
changes when that swap happens.

Security notes (self-asserted identity, session-ownership on resume): see
``docs/SECURITY.md`` §1-2.
"""

from __future__ import annotations

from fastapi import Depends, Request

from agent.identity import Principal
from agent.profiles import get_profile
from service.core.config import Settings, get_settings

_AGENT_PROFILE_HEADER = "X-Agent-Profile"


def get_principal(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Principal | None:
    if not settings.is_development:
        return None

    profile = get_profile(request.headers.get(_AGENT_PROFILE_HEADER))
    return profile.principal_from_headers(request.headers)
