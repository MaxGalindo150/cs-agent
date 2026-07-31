"""Identity seam: where a verified end-user arrives from the transport.

STUB — trusts the ``X-User-Id``/``X-User-Email`` headers verbatim, no
verification happens here. Neither this service nor the frontend has real
auth yet (a deliberate, temporary relaxation of "treat every inbound message
as untrusted" — CLAUDE.md's engineering bar), so this only runs in dev
(``settings.is_development``); everywhere else it returns ``None`` rather than
let an unverified header silently become staging/prod's auth.

When real auth lands, only this function's body changes (verify a bearer JWT,
extract its subject claim instead of trusting a header) — its shape
(``-> Principal | None``) stays the same, so no route or agent-layer code
changes when that swap happens.

Security notes (self-asserted identity, session-ownership on resume): see
``docs/SECURITY.md`` §1-2.
"""

from __future__ import annotations

from fastapi import Depends, Header

from agent.identity import Principal
from service.core.config import Settings, get_settings

_USER_ID_HEADER = "X-User-Id"
_USER_EMAIL_HEADER = "X-User-Email"


def get_principal(
    settings: Settings = Depends(get_settings),
    x_user_id: str | None = Header(default=None, alias=_USER_ID_HEADER),
    x_user_email: str | None = Header(default=None, alias=_USER_EMAIL_HEADER),
) -> Principal | None:
    if not settings.is_development or not x_user_id:
        return None
    return Principal(user_id=x_user_id, email=x_user_email)
