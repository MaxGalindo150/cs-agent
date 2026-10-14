"""Principal — the identified end-user a turn is scoped to (or None).

Provider- and transport-neutral (CLAUDE.md §4): this lives under ``agent/``,
not ``service/``, because tool implementations under ``agent/tools/`` will
need to name this type. *How* a Principal is obtained (a verified session
token from the embedded widget, or the dev-only trusted header) is entirely a
``service/`` concern — see ``service/core/identity.py``. Every downstream
consumer depends only on this type, never on how it was resolved.

Two audiences share the agent: Cashea's end customers and aliados — employees
of the merchants that sell with Cashea. Which one a turn is for decides the
soul, the skills and the tools it gets (see ``audience_of``). The merchant
fields come from Cashea's backend for a verified merchant employee, never
from anything the caller asserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Audience = Literal["consumer", "merchant"]
AUDIENCES: tuple[Audience, ...] = ("consumer", "merchant")


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    email: str | None = None
    merchant_id: str | None = None
    merchant_name: str | None = None
    store_id: str | None = None
    store_uuid: str | None = None
    store_name: str | None = None
    role: str | None = None


def audience_of(principal: Principal | None) -> Audience:
    """A merchant employee is an aliado; anyone else — including an anonymous
    visitor — is a consumer."""
    if principal is not None and principal.merchant_id is not None:
        return "merchant"
    return "consumer"
