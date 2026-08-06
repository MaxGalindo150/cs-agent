"""External-tool wiring: the HTTP clients the agent's tools call.

One client per profile, built in the app lifespan and stored on
``app.state.profiles`` (see ``service/core/profiles.py``); the request path
resolves one by header. This module owns only the transport rules every backend
client must obey.
"""

from __future__ import annotations

import httpx
from fastapi import Request

from agent.profiles import get_profile
from agent.tools.registry import ToolRegistry
from service.core.config import Settings


def build_backend_client(url: str, settings: Settings, name: str) -> httpx.AsyncClient:
    """Client for a backend the tools call, with the transport rules we require.

    Tool traffic carries phone numbers, one-time codes and order data, so
    cleartext is refused outside dev: a deployed config pointing at ``http://``
    fails at startup rather than shipping that over the wire. ``localhost`` and
    the compose service names stay on http because the local mocks speak it.

    ``follow_redirects`` is pinned off (httpx's default today) so a redirect
    can never re-send a request body to a host we did not configure.
    """
    if not url.startswith("https://") and not settings.is_development:
        raise ValueError(
            f"{name} must use https outside dev (ENVIRONMENT={settings.environment}); "
            f"got {url!r}"
        )
    return httpx.AsyncClient(base_url=url, timeout=10.0, follow_redirects=False)


def get_registry(request: Request) -> ToolRegistry:
    """Dependency: the tool registry for the requested profile."""
    profile = get_profile(request.headers.get("X-Agent-Profile"))
    registry: ToolRegistry = request.app.state.profiles[profile.name].registry
    return registry
