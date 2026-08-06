"""The buyer profile — Cheo for end customers of the BNPL product."""

from __future__ import annotations

from collections.abc import Mapping

from agent.identity import Principal
from agent.profiles.base import Profile
from agent.prompts import load_prompt
from agent.tools import build_registry

_USER_ID = "x-user-id"
_USER_EMAIL = "x-user-email"


def _principal_from_headers(headers: Mapping[str, str]) -> Principal | None:
    """The buyer identity the host app asserts.

    Header-trust caveats live in ``service/core/identity.py`` and
    ``docs/SECURITY.md`` §1 — this only maps headers to a ``Principal``.
    """
    user_id = headers.get(_USER_ID)
    if not user_id:
        return None
    return Principal(user_id=user_id, email=headers.get(_USER_EMAIL))


BUYER = Profile(
    name="buyer",
    soul=load_prompt("buyer"),
    build_registry=build_registry,
    backend_url_setting="bnpl_api_url",
    principal_from_headers=_principal_from_headers,
)
