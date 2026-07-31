"""The agent's tools. `build_registry` assembles them, bound to the external
clients/resources they need (the BNPL HTTP client, the memory database). The
service builds those at startup and hands them in; the registry itself stays
provider-neutral.
"""

from __future__ import annotations

import httpx

from agent.memory.db import Database
from agent.tools.implementations.bnpl.orders import (
    make_get_my_orders_tool,
    make_get_order_tool,
)
from agent.tools.implementations.memory import make_manage_memory_tool
from agent.tools.registry import ToolRegistry


def build_registry(bnpl_client: httpx.AsyncClient, db: Database) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(make_get_order_tool(bnpl_client))
    registry.register(make_get_my_orders_tool(bnpl_client))
    registry.register(make_manage_memory_tool(db))
    return registry
