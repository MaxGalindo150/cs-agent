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
    # ── Merchant profile (None for the buyer profile) ──
    # The merchant principal is a triplet: merchant (RIF) → store → employee.
    # ``profile`` distinguishes buyer from merchant so the wiring layer can
    # select the right agent + toolset without inspecting individual fields.
    profile: str = "buyer"  # "buyer" | "merchant"
    merchant_id: str | None = None
    store_uuid: str | None = None
    employee_id: str | None = None
    role: str | None = None  # ADMIN | MANAGER | CASHIER
