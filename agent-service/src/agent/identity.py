"""Principal — the identified end-user a turn is scoped to (or None).

Provider- and transport-neutral (CLAUDE.md §4): this lives under ``agent/``,
not ``service/``, because tool implementations under ``agent/tools/`` will
need to name this type. *How* a Principal is obtained (a verified session
token from the embedded widget, or the dev-only trusted header) is entirely a
``service/`` concern — see ``service/core/identity.py``. Every downstream
consumer depends only on this type, never on how it was resolved.

Not a tenant/org concept — multi-tenancy is a deliberate later phase
(CLAUDE.md §9). The merchant fields only say which merchant/store a merchant
employee belongs to (from the host's verified token); they are None for any
other caller.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    email: str | None = None
    merchant_id: str | None = None
    store_id: str | None = None
    role: str | None = None
