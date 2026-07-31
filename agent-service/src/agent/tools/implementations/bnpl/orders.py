"""BNPL order tools — read-only lookups against the external BNPL system.

Built by a `make_*_tool` factory bound to a shared `httpx.AsyncClient` (base URL
from config), so it is testable with a mock transport — no running server, no
network. The return string always says exactly what happened; missing args and
failures come back as honest text, never a raised exception.

Amounts from the BNPL API are in **cents** — the tool passes the raw JSON through
and the description tells the model to divide by 100.

Identity-gated (`requires_identity=True`, docs/SECURITY.md §3): a customer
gives an order id, but that alone must not let them (or the model, hallucinated
or not) read someone else's order. The mock BNPL backend's order carries its
own `userId` (mock-server/src/schema/order.ts) — this tool verifies it matches
the caller's `Principal` before returning anything, the same "id + owner, one
check" shape as `FactRepository.update`/`.delete`.
"""

from __future__ import annotations

import json

import httpx

from agent.tools.context import ToolContext
from agent.tools.registry import Tool


def make_get_order_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order(ctx: ToolContext, order_id: str = "") -> str:
        assert ctx.principal is not None  # guaranteed by requires_identity
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
        try:
            order = resp.json()
        except json.JSONDecodeError:
            return f"Could not look up order '{order_id}' (bad response from service)."
        # Never trust order_id alone as proof of ownership: only return an
        # order that actually belongs to the caller, never one merely guessed
        # or hallucinated. The message is deliberately the same shape as "not
        # found" — it doesn't confirm the order exists for someone else.
        if order.get("userId") != ctx.principal.user_id:
            return f"No order found with id '{order_id}'."
        return resp.text

    return Tool(
        name="get_order",
        progress_label="Getting order {order_id}",
        description=(
            "Look up one of the current customer's own BNPL orders by its id "
            "(e.g. 'ord_0001'). Returns the order's status, items, plan, and "
            "amounts. Amounts are in cents — divide by 100 for the currency value. "
            "Only works for orders belonging to the identified customer."
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
        requires_identity=True,
    )


def make_get_my_orders_tool(client: httpx.AsyncClient) -> Tool:
    """ "What's the status of my orders?" — no id required, unlike `get_order`.

    ``input_schema`` has zero properties on purpose: there is nothing for the
    model to fill in, so a hallucinated ``user_id``/``userId`` argument has
    nowhere to go. The caller's id comes only from ``ctx.principal`` — never
    from anything the model supplies.
    """

    async def get_my_orders(ctx: ToolContext) -> str:
        assert ctx.principal is not None  # guaranteed by requires_identity
        try:
            resp = await client.get(
                "/api/v1/orders", params={"userId": ctx.principal.user_id}
            )
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return f"Could not look up your orders (status {resp.status_code})."
        return resp.text

    return Tool(
        name="get_my_orders",
        progress_label="Getting your orders",
        description=(
            "List the current customer's own BNPL orders — status, items, plan, "
            "and amounts for each. Use this for 'what's the status of my orders?' "
            "style questions where the customer doesn't give a specific order id "
            "(use get_order instead when they do). Amounts are in cents — divide "
            "by 100 for the currency value."
        ),
        input_schema={"type": "object", "properties": {}},
        fn=get_my_orders,
        requires_identity=True,
    )
