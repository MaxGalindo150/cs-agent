"""BNPL order tools — read-only lookups against the external BNPL system.

Built by a `make_*_tool` factory bound to a shared `httpx.AsyncClient` (base URL
from config), so it is testable with a mock transport — no running server, no
network. The return string always says exactly what happened; missing args and
failures come back as honest text, never a raised exception.

Amounts from the BNPL API are in **cents** — the tool passes the raw JSON through
and the description tells the model to divide by 100.
"""

from __future__ import annotations

import httpx

from agent.tools.registry import Tool


def make_get_order_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order(order_id: str = "") -> str:
        # Defensive: models sometimes emit an empty/partial tool call. Give the
        # model something it can recover from, not a raw error.
        if not order_id:
            return (
                "get_order needs an order_id (e.g. 'ord_0001'). Call it again with one."
            )
        try:
            resp = await client.get(f"/api/v1/orders/{order_id}")
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if resp.status_code == 404:
            return f"No order found with id '{order_id}'."
        if resp.status_code != 200:
            return f"Could not look up order '{order_id}' (status {resp.status_code})."
        return resp.text

    return Tool(
        name="get_order",
        progress_label="Getting order {order_id}",
        description=(
            "Look up a BNPL order by its id (e.g. 'ord_0001'). Returns the order's "
            "status, items, plan, and amounts. Amounts are in cents — divide by 100 "
            "for the currency value."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order id, e.g. 'ord_0001'.",
                }
            },
            "required": ["order_id"],
        },
        fn=get_order,
    )
