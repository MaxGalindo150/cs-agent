"""The merchant profile — Cheo for Cashea's aliados (merchant portal)."""

from __future__ import annotations

from collections.abc import Mapping

from agent.identity import Principal
from agent.profiles.base import Profile
from agent.prompts import load_prompt
from agent.tools import build_merchant_registry

_MERCHANT_ID = "x-merchant-id"
_EMPLOYEE_ID = "x-employee-id"


def _principal_from_headers(headers: Mapping[str, str]) -> Principal | None:
    """The merchant identity the portal asserts.

    Anonymous portal visitors resolve to no principal, which is what makes the
    merchant-scoped tools unavailable to them (they all require identity), so a
    visitor is never asked for a RIF in chat.

    The synthetic ``merchant:<id>`` user id keys the memory facade without
    colliding with buyer ids.
    """
    merchant_id = headers.get(_MERCHANT_ID)
    if not merchant_id:
        return None
    return Principal(
        user_id=f"merchant:{merchant_id}",
        profile="merchant",
        merchant_id=merchant_id,
        employee_id=headers.get(_EMPLOYEE_ID),
    )


MERCHANT = Profile(
    name="merchant",
    soul=load_prompt("merchant"),
    build_registry=build_merchant_registry,
    backend_url_setting="merchant_api_url",
    principal_from_headers=_principal_from_headers,
)
