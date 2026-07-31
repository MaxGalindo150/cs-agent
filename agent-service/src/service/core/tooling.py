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


def build_bnpl_client(settings: Settings) -> httpx.AsyncClient:
    """Process-wide HTTP client for the BNPL backend (base URL from config)."""
    return httpx.AsyncClient(base_url=settings.bnpl_api_url, timeout=10.0)


def get_registry(request: Request) -> ToolRegistry:
    """Dependency: the tool registry assembled at startup."""
    registry: ToolRegistry = request.app.state.registry
    return registry
