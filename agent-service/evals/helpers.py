"""Shared eval plumbing: a real-``Agent`` factory and a live-mock-server
identity lookup, mirroring Waku's ``evals/helpers.py`` (``HAS_KEY`` +
``make_waku``) adapted to this service's shape.

Unlike Waku, a turn here always needs Postgres for session state (CLAUDE.md
§9) — the ``database`` fixture (a real, migrated Postgres) comes from
``evals/conftest.py``, not from here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from anthropic import AsyncAnthropic

from agent.app import Agent, build_agent
from agent.memory.db import Database
from agent.tools import build_registry
from service.core.config import get_settings

# True only when a real Anthropic key is configured — never the placeholder
# tests/conftest.py sets for Level 1 (config-validation-only) tests. Live
# evals are skipped, not failed, without one: they need a real model call.
HAS_KEY = (
    bool(os.getenv("ANTHROPIC_API_KEY"))
    and os.getenv("ANTHROPIC_API_KEY") != "test-key-not-used"
)


@asynccontextmanager
async def make_agent_live(database: Database) -> AsyncIterator[Agent]:
    """Assemble a real ``Agent`` — the real Anthropic client, the real BNPL
    mock-server, the real tool registry — over the eval Postgres. Calls the
    same ``build_agent`` factory the transport lifespan and ``tests/integration``
    use, so the eval can't drift from how production assembles the ``Agent``.

    An async context manager (not a plain factory) because both clients it
    opens are otherwise never closed — ``Agent`` doesn't own them, matching
    how ``service/main.py``'s lifespan is the one that calls
    ``llm.close()``/``bnpl.aclose()`` in production; here that's this
    function's job instead, once per eval case.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    bnpl_client = httpx.AsyncClient(base_url=settings.bnpl_api_url)
    try:
        tools = build_registry(bnpl_client, database)
        yield build_agent(
            client=client,
            db=database,
            tools=tools,
            chat_model=settings.anthropic_chat_model,
            fast_model=settings.anthropic_fast_model,
        )
    finally:
        await client.close()
        await bnpl_client.aclose()


def resolve_demo_user(scenario_tag: str) -> str:
    """The seeded demo user id tagged with ``scenario_tag`` (e.g.
    "shipment_stuck", "double_payment") — resolved against the LIVE
    mock-server rather than hardcoded, because it reseeds with a random id
    suffix on every restart (``usr_002r``, not a stable ``usr_0002``).

    Dataset cases reference the stable scenario tag; only this lookup, run at
    eval time, needs to know the tag -> current-id mapping.
    """
    settings = get_settings()
    resp = httpx.get(f"{settings.bnpl_api_url}/api/v1/users", timeout=10.0)
    resp.raise_for_status()
    for user in resp.json()["data"]:
        if scenario_tag in user.get("scenarioTags", []):
            return str(user["id"])
    raise LookupError(f"no seeded demo user tagged {scenario_tag!r}")
