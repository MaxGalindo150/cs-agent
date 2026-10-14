"""The one way merchant tools call Cashea's merchant API.

Turns every failure into text the model can relay honestly (the tools never
raise), and keeps the credential out of anything returned: errors name the
situation, never echo the request.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from agent.tools.context import ToolContext

NO_CREDENTIAL = (
    "Can't reach this aliado's store data in this conversation right now. "
    "Ask them to reload the portal and try again."
)
UNAVAILABLE = "The store data service is unavailable right now — try again shortly."
NO_ACCESS = (
    "This aliado's user doesn't have access to that information. An admin of "
    "their store can check it."
)


@dataclass(frozen=True, slots=True)
class Found:
    data: Any


async def merchant_get(
    client: httpx.AsyncClient,
    ctx: ToolContext,
    path: str,
    params: list[tuple[str, str]] | None = None,
) -> Found | str | None:
    """``Found`` on 200, ``None`` on 404, otherwise text for the model."""
    if not ctx.host_credential:
        return NO_CREDENTIAL
    try:
        resp = await client.get(
            path,
            params=tuple(params or ()),
            headers={"Authorization": f"Bearer {ctx.host_credential}"},
        )
    except httpx.RequestError:
        return UNAVAILABLE
    if resp.status_code == 404:
        return None
    if resp.status_code in (401, 403):
        return NO_ACCESS
    if resp.status_code != 200:
        return f"The store data service returned an error (status {resp.status_code})."
    try:
        return Found(resp.json())
    except json.JSONDecodeError:
        return "The store data service sent an unreadable response."
