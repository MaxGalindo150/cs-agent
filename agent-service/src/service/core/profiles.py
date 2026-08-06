"""Per-profile assembly: one HTTP client, registry and Agent for each profile.

This is the seam where ``Settings`` meets a ``Profile``: the profile declares
*which* config field holds its backend URL, this module reads it and hands plain
values to the brain-side factories (CLAUDE.md §4 — nothing under ``agent/`` sees
``Settings``).

The lifespan builds one runtime per registered profile and stores them on
``app.state.profiles``; the request path resolves one by header.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from anthropic import AsyncAnthropic

from agent.app import Agent
from agent.memory.db import Database
from agent.memory.embeddings import Embedder
from agent.profiles import PROFILES, Profile
from agent.tools.registry import ToolRegistry
from service.core.agent import build_service_agent
from service.core.config import Settings
from service.core.tooling import build_backend_client


@dataclass(frozen=True)
class ProfileRuntime:
    """Everything one profile needs at request time, built once at startup."""

    profile: Profile
    client: httpx.AsyncClient
    registry: ToolRegistry
    agent: Agent


def build_profile_runtime(
    profile: Profile,
    settings: Settings,
    *,
    llm: AsyncAnthropic,
    db: Database,
    embedder: Embedder | None,
) -> ProfileRuntime:
    """Assemble one profile: backend client → tool registry → Agent."""
    url = getattr(settings, profile.backend_url_setting)
    client = build_backend_client(url, settings, profile.backend_url_setting.upper())
    registry = profile.build_registry(client, db)
    agent = build_service_agent(
        settings,
        client=llm,
        db=db,
        tools=registry,
        embedder=embedder,
        soul=profile.soul,
    )
    return ProfileRuntime(
        profile=profile, client=client, registry=registry, agent=agent
    )


def build_profile_runtimes(
    settings: Settings,
    *,
    llm: AsyncAnthropic,
    db: Database,
    embedder: Embedder | None,
) -> dict[str, ProfileRuntime]:
    """One runtime per registered profile, keyed by profile name."""
    return {
        name: build_profile_runtime(
            profile, settings, llm=llm, db=db, embedder=embedder
        )
        for name, profile in PROFILES.items()
    }
