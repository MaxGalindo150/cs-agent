"""Principal — the identified end-user a turn is scoped to (or None).

Provider- and transport-neutral (CLAUDE.md §4): this lives under ``agent/``,
not ``service/``, because tool implementations under ``agent/tools/`` will
need to name this type. *How* a Principal is obtained (today: a trusted dev
header; later: a verified JWT) is entirely a ``service/`` concern — see
``service/core/identity.py``. Every downstream consumer depends only on this
type, never on how it was resolved, so that future swap touches no other file.

Not a tenant/org concept — multi-tenancy is a deliberate later phase
(CLAUDE.md §9). One end-user, no isolation semantics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    email: str | None = None
