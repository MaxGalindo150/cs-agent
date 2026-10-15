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
    make_get_order_installments_tool,
    make_get_order_shipment_tool,
    make_get_order_tool,
)
from agent.tools.implementations.bnpl.transactions import make_get_transactions_tool
from agent.tools.implementations.escalation import make_escalate_to_human_tool
from agent.tools.implementations.memory import make_manage_memory_tool
from agent.tools.implementations.merchant.daily_closing import (
    make_get_daily_closing_tool,
)
from agent.tools.implementations.merchant.orders import (
    make_get_order_detail_tool,
    make_search_orders_tool,
)
from agent.tools.implementations.merchant.reports import make_get_monthly_report_tool
from agent.tools.implementations.merchant.suggestions import make_suggest_replies_tool
from agent.tools.implementations.present_choice import make_present_choice_tool
from agent.tools.registry import ToolRegistry


def build_registry(
    bnpl_client: httpx.AsyncClient,
    db: Database,
    merchant_client: httpx.AsyncClient | None = None,
) -> ToolRegistry:
    """``merchant_client`` is Cashea's merchant API; without it the aliado
    tools aren't registered at all (aliados then get only the shared tools)."""
    registry = ToolRegistry()
    registry.register(make_get_order_tool(bnpl_client))
    registry.register(make_get_order_shipment_tool(bnpl_client))
    registry.register(make_get_order_installments_tool(bnpl_client))
    registry.register(make_get_my_orders_tool(bnpl_client))
    registry.register(make_get_transactions_tool(bnpl_client))
    registry.register(make_manage_memory_tool(db))
    registry.register(make_escalate_to_human_tool(db))
    registry.register(make_present_choice_tool())
    registry.register(make_suggest_replies_tool())
    if merchant_client is not None:
        registry.register(make_search_orders_tool(merchant_client))
        registry.register(make_get_order_detail_tool(merchant_client))
        registry.register(make_get_monthly_report_tool(merchant_client))
        registry.register(make_get_daily_closing_tool(merchant_client))
    return registry
