"""The agent's tools. `build_registry` assembles them, bound to the external
clients/resources they need (the BNPL HTTP client, the memory database). The
service builds those at startup and hands them in; the registry itself stays
provider-neutral.

`build_merchant_registry` does the same for the merchant (aliado) profile —
bound to the merchant HTTP client instead of the BNPL one.
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
from agent.tools.implementations.merchant.auth import (
    make_get_employee_2fa_tool,
    make_register_2fa_phone_tool,
)
from agent.tools.implementations.merchant.catalog import (
    make_list_merchant_stores_tool,
)
from agent.tools.implementations.merchant.finance import (
    make_get_daily_conciliation_tool,
    make_get_invoices_tool,
    make_get_monthly_report_tool,
    make_get_payouts_tool,
)
from agent.tools.implementations.merchant.orders import (
    make_cancel_order_tool,
    make_get_cancellation_reasons_tool,
    make_get_order_detail_tool,
    make_list_merchant_orders_tool,
)
from agent.tools.implementations.merchant.orders import (
    make_get_order_installments_tool as make_merchant_installments_tool,
)
from agent.tools.implementations.present_choice import make_present_choice_tool
from agent.tools.registry import ToolRegistry


def build_registry(bnpl_client: httpx.AsyncClient, db: Database) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(make_get_order_tool(bnpl_client))
    registry.register(make_get_order_shipment_tool(bnpl_client))
    registry.register(make_get_order_installments_tool(bnpl_client))
    registry.register(make_get_my_orders_tool(bnpl_client))
    registry.register(make_get_transactions_tool(bnpl_client))
    registry.register(make_manage_memory_tool(db))
    registry.register(make_escalate_to_human_tool(db))
    registry.register(make_present_choice_tool())
    return registry


def build_merchant_registry(
    merchant_client: httpx.AsyncClient, db: Database
) -> ToolRegistry:
    """Assemble the toolset for the merchant (aliado) support agent.

    Completely separate from the buyer registry — the merchant agent never
    sees buyer tools (get_my_orders, get_transactions) and vice versa. Both
    share ``manage_memory`` and ``escalate_to_human`` (profile-agnostic).
    """
    registry = ToolRegistry()
    # ── Catálogo scoped al merchant ──
    registry.register(make_list_merchant_stores_tool(merchant_client))
    # ── Órdenes ──
    registry.register(make_list_merchant_orders_tool(merchant_client))
    registry.register(make_get_order_detail_tool(merchant_client))
    registry.register(make_merchant_installments_tool(merchant_client))
    registry.register(make_get_cancellation_reasons_tool(merchant_client))
    registry.register(make_cancel_order_tool(merchant_client))
    # ── Finanzas ──
    registry.register(make_get_payouts_tool(merchant_client))
    registry.register(make_get_invoices_tool(merchant_client))
    registry.register(make_get_monthly_report_tool(merchant_client))
    registry.register(make_get_daily_conciliation_tool(merchant_client))
    # ── Autenticación / 2FA ──
    registry.register(make_get_employee_2fa_tool(merchant_client))
    registry.register(make_register_2fa_phone_tool(merchant_client))
    # ── Compartidos ──
    registry.register(make_manage_memory_tool(db))
    registry.register(make_escalate_to_human_tool(db))
    registry.register(make_present_choice_tool())
    return registry
