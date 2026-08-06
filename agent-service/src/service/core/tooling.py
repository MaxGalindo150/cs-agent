"""External-tool wiring: the HTTP client the agent's tools call, and the tool
registry built from it.

The registry is assembled once in the app lifespan (bound to the process-wide
BNPL client) and stored on `app.state`; routes read it through `get_registry`.
"""

from __future__ import annotations

import httpx
from fastapi import Request

from agent.tools.registry import ToolRegistry
from service.core.config import Settings


def _backend_client(url: str, settings: Settings, name: str) -> httpx.AsyncClient:
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


def build_bnpl_client(settings: Settings) -> httpx.AsyncClient:
    """Process-wide HTTP client for the BNPL backend (base URL from config)."""
    return _backend_client(settings.bnpl_api_url, settings, "BNPL_API_URL")


def build_merchant_client(settings: Settings) -> httpx.AsyncClient:
    """Process-wide HTTP client for the merchant backend (base URL from config)."""
    return _backend_client(settings.merchant_api_url, settings, "MERCHANT_API_URL")


def get_registry(request: Request) -> ToolRegistry:
    """Dependency: the tool registry assembled at startup."""
    registry: ToolRegistry = request.app.state.registry
    return registry
