"""The agent's tools. `build_registry` assembles them, bound to the external
clients they need (currently the BNPL HTTP client). The service builds those
clients at startup and hands them in; the registry itself stays provider-neutral.
"""

from __future__ import annotations

import httpx

from agent.tools.implementations.bnpl.orders import make_get_order_tool
from agent.tools.registry import ToolRegistry


def build_registry(bnpl_client: httpx.AsyncClient) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(make_get_order_tool(bnpl_client))
    return registry
