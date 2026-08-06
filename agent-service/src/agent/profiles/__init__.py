"""The profile registry — the one list the service iterates.

Adding an audience is: a prompt in ``agent/prompts/<name>.md``, a registry
factory in ``agent/tools/__init__.py``, a backend URL field in ``Settings``, and
a module here added to ``_REGISTERED``. Nothing in ``service/`` changes — the
lifespan builds a client, registry and agent for every entry, ``get_agent``
looks one up by header, and ``get_principal`` delegates to it.

An unknown or absent ``X-Agent-Profile`` resolves to the buyer profile, so a
host app that never heard of profiles keeps working.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from agent.profiles.base import Profile
from agent.profiles.buyer import BUYER
from agent.profiles.merchant import MERCHANT

_REGISTERED = (BUYER, MERCHANT)

DEFAULT_PROFILE = BUYER.name

PROFILES: Mapping[str, Profile] = MappingProxyType({p.name: p for p in _REGISTERED})


def get_profile(name: str | None) -> Profile:
    """The profile for ``name``, falling back to the default one.

    Unknown values fall back rather than raise: the header is attacker-supplied
    and a bad one must not become a 500. Falling back to the buyer profile is
    also the safe direction — merchant tools require a merchant principal, which
    the buyer header set cannot produce.
    """
    if name is None:
        return PROFILES[DEFAULT_PROFILE]
    return PROFILES.get(name, PROFILES[DEFAULT_PROFILE])


__all__ = ["DEFAULT_PROFILE", "PROFILES", "Profile", "get_profile"]
