"""Shared pytest fixtures and hermetic test environment.

Tests must not depend on a local ``.env`` — that file is git-ignored and absent
in CI. Required settings are injected into the environment here, *before*
``agent.*`` is imported (pytest loads conftest before any test module), so
``get_settings()`` reads deterministic values regardless of the machine.

The injected Anthropic key is a non-secret placeholder: Level 1 tests never call
the provider, they only need config validation to pass so the app can boot.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
os.environ.setdefault("VOYAGE_API_KEY", "test-key-not-used")
os.environ.setdefault("ENVIRONMENT", "dev")
# Tests own their schema (integration migrates a dedicated test DB); never let a
# lifespan that happens to run migrate against a real database mid-suite.
os.environ.setdefault("RUN_MIGRATIONS_ON_STARTUP", "false")

from service.main import create_app  # noqa: E402  (must follow env injection above)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """In-process HTTP client bound to a fresh app instance (no network)."""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
