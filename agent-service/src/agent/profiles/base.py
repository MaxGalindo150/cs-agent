"""What a profile *is*.

A profile is one audience the agent serves: a persona, the toolset that
audience is allowed to reach, the backend those tools call, and how the
transport says who is on the other end. Everything else — the loop, memory,
sessions, tracing, budgets — is shared, which is why these are profiles inside
one service and not separate services.

The point of gathering the four pieces in one frozen record is that adding an
audience is adding a module, not editing five call sites. ``service/`` iterates
whatever is registered in ``agent/profiles/__init__.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

from agent.identity import Principal
from agent.memory.db import Database
from agent.tools.registry import ToolRegistry

RegistryFactory = Callable[[httpx.AsyncClient, Database], ToolRegistry]
PrincipalReader = Callable[[Mapping[str, str]], Principal | None]


@dataclass(frozen=True)
class Profile:
    """One audience, with everything that differs for it.

    ``backend_url_setting`` is the *name* of the ``Settings`` field holding this
    profile's backend URL, not the URL itself: ``agent/`` must not import the
    service's ``Settings`` (CLAUDE.md §4 — the brain never depends on the
    transport). ``service/core/profiles.py`` resolves it, and
    ``test_profiles.py`` asserts every declared name exists so a typo fails a
    test instead of a boot.

    ``principal_from_headers`` receives a case-insensitive header mapping
    (Starlette's) and reads it with lowercase keys.
    """

    name: str
    soul: str
    build_registry: RegistryFactory
    backend_url_setting: str
    principal_from_headers: PrincipalReader
