"""Aliado cierre de caja — today's totals and when the store last closed.

``GET /stores/v2/{store}/dailyConciliation`` (today, so far) and
``GET /stores/v2/{store}/dailyConciliation/last`` on Cashea's merchant API,
with the aliado's own token. Only for the store the employee is assigned to:
that's the store the portal's "Cierre de caja" shows, and the API answers 401
for any other — even to an admin of the merchant. Amounts in dollars.

The last closing also decides whether a manager or cashier may still cancel
an order: only orders created after it (merchant-web OrderDetails.helper.ts).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from agent import clock
from agent.tools.context import ToolContext
from agent.tools.implementations.merchant._http import Found, merchant_get
from agent.tools.registry import Tool

# Staging answers in ~12s (today) and ~6s (last); the shared client gives
# up at 5s.
_TIMEOUT_SECONDS = 20.0
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def make_get_daily_closing_tool(client: httpx.AsyncClient) -> Tool:
    async def get_daily_closing(ctx: ToolContext) -> str:
        principal = ctx.principal
        store_uuid = principal.store_uuid if principal else None
        if not store_uuid or not _UUID.match(store_uuid):
            return (
                "This aliado's user has no store assigned, so there's no "
                "cierre de caja to read."
            )
        base = f"/stores/v2/{store_uuid}/dailyConciliation"

        today, last = await asyncio.gather(
            merchant_get(client, ctx, base, timeout=_TIMEOUT_SECONDS),
            merchant_get(client, ctx, f"{base}/last", timeout=_TIMEOUT_SECONDS),
        )
        if not isinstance(today, Found):
            return today or "No cierre de caja data for this store."
        last_at = last.data.get("createdAt") if isinstance(last, Found) else None

        return json.dumps(
            {
                "store": principal.store_name if principal else None,
                "today_so_far": _totals(today.data),
                "by_caja": [
                    {"caja": (p.get("pos") or {}).get("name"), **_totals(p)}
                    for p in today.data.get("conciliationsByPos") or []
                ],
                "last_closing_at": clock.describe(last_at) if last_at else None,
                "closed_today": _is_today(last_at),
            },
            ensure_ascii=False,
        )

    return Tool(
        name="get_daily_closing",
        progress_label="Revisando el cierre de caja",
        description=(
            "The aliado's own store's cierre de caja: today's orders so far, "
            "total facturado and total financiado por Cashea (dollars), per "
            "caja, and when the store last did its cierre (and whether that "
            "was today). Use it for 'how much did I sell today', 'was the "
            "cierre done', and to tell a manager or cashier whether an order "
            "is still cancellable: it is while no cierre has happened since "
            "the order was created (created_at later than last_closing_at). "
            "Only covers the store the employee is assigned to."
        ),
        input_schema={"type": "object", "properties": {}},
        fn=get_daily_closing,
        requires_identity=True,
        audiences=frozenset({"merchant"}),
    )


def _totals(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "orders": data.get("ordersCount"),
        "total_facturado": data.get("totalChargedAmount"),
        "total_financiado_por_cashea": data.get("totalFinancedAmount"),
    }


def _is_today(value: Any) -> bool | None:
    moment = clock.local(value)
    return moment.date() == clock.now().date() if moment else None
