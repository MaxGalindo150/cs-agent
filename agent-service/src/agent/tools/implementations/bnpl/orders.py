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

import asyncio
import json
from typing import Any

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


def make_get_order_shipment_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order_shipment(ctx: ToolContext, order_id: str = "") -> str:
        assert ctx.principal is not None  # guaranteed by requires_identity
        if not order_id:
            return (
                "get_order_shipment needs an order_id (e.g. 'ord_0001'). "
                "Call it again with one."
            )
        try:
            resp = await client.get(f"/api/v1/orders/{order_id}/shipment")
        except httpx.RequestError:
            return "The shipping service is unavailable right now — try again shortly."
        if resp.status_code == 404:
            return f"No shipment found for order '{order_id}'."
        if resp.status_code != 200:
            return (
                f"Could not look up the shipment for order '{order_id}' "
                f"(status {resp.status_code})."
            )
        try:
            shipment = resp.json()
        except json.JSONDecodeError:
            return (
                f"Could not look up the shipment for order '{order_id}' "
                "(bad response from service)."
            )
        # Same "id + owner, one check" shape as get_order — the shipment
        # carries its own userId (mock-server/src/schema/shipment.ts), so no
        # separate order lookup is needed to enforce it.
        if shipment.get("userId") != ctx.principal.user_id:
            return f"No shipment found for order '{order_id}'."
        return resp.text

    return Tool(
        name="get_order_shipment",
        progress_label="Tracking shipment for order {order_id}",
        description=(
            "Track the shipment for one of the current customer's own BNPL "
            "orders — carrier, tracking number, delivery status, and the full "
            "tracking event history. Use this for 'where is my package?' or "
            "'why is my order stuck?' style questions. Only works for orders "
            "belonging to the identified customer."
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
        fn=get_order_shipment,
        requires_identity=True,
    )


def make_get_order_installments_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order_installments(ctx: ToolContext, order_id: str = "") -> str:
        assert ctx.principal is not None  # guaranteed by requires_identity
        if not order_id:
            return (
                "get_order_installments needs an order_id (e.g. 'ord_0001'). "
                "Call it again with one."
            )
        try:
            resp = await client.get(f"/api/v1/orders/{order_id}/installments")
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if resp.status_code == 404:
            return f"No order found with id '{order_id}'."
        if resp.status_code != 200:
            return (
                f"Could not look up installments for order '{order_id}' "
                f"(status {resp.status_code})."
            )
        try:
            body = resp.json()
        except json.JSONDecodeError:
            return (
                f"Could not look up installments for order '{order_id}' "
                "(bad response from service)."
            )
        installments = body.get("data", [])
        # Every installment carries its own userId (mock-server/src/schema/
        # installment.ts), generated for the same order/user by construction
        # — checking it enforces "id + owner, one check" without a second
        # round trip to fetch the order itself. An order with zero
        # installments can't be proven to belong to the caller, so it's
        # refused the same as a 404 rather than returned unchecked.
        if not installments or installments[0].get("userId") != ctx.principal.user_id:
            return f"No order found with id '{order_id}'."
        return resp.text

    return Tool(
        name="get_order_installments",
        progress_label="Getting installments for order {order_id}",
        description=(
            "List the payment installments for one of the current customer's own "
            "BNPL orders — due date, amount, and status (paid, due, overdue, "
            "failed) for each. Use this to check whether a specific charge went "
            "through, was missed, or is upcoming. Amounts are in cents — divide "
            "by 100 for the currency value. Only works for orders belonging to "
            "the identified customer."
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
        fn=get_order_installments,
        requires_identity=True,
    )


async def _shipment_summary(
    client: httpx.AsyncClient, order_id: str, user_id: str
) -> dict[str, Any]:
    """Best-effort shipment fields to fold into an order the caller already
    owns — a lookup failure here just means that one order has no shipment
    info attached, never an error for the whole list.

    The order list is already filtered server-side by ``userId``, but this
    still checks the shipment's own ``userId`` before using it — the same
    "id + owner, one check" invariant as `get_order_shipment`, not just trust
    that the upstream filter was applied correctly.
    """
    try:
        resp = await client.get(f"/api/v1/orders/{order_id}/shipment")
    except httpx.RequestError:
        return {}
    if resp.status_code != 200:
        return {}
    try:
        shipment = resp.json()
    except json.JSONDecodeError:
        return {}
    if shipment.get("userId") != user_id:
        return {}
    return {
        "shipmentStatus": shipment.get("status"),
        "shippedAt": shipment.get("shippedAt"),
        "estimatedDelivery": shipment.get("estimatedDelivery"),
    }


def make_get_my_orders_tool(client: httpx.AsyncClient) -> Tool:
    """ "What's the status of my orders?" — no id required, unlike `get_order`.

    ``input_schema`` has zero properties on purpose: there is nothing for the
    model to fill in, so a hallucinated ``user_id``/``userId`` argument has
    nowhere to go. The caller's id comes only from ``ctx.principal`` — never
    from anything the model supplies.

    Each order's ``status`` is a *financing* status (pending/approved/active/
    completed/defaulted/cancelled) — it says nothing about delivery. Without
    shipment info folded in, a customer who says "my order hasn't arrived" but
    doesn't know which one forces the model into either guessing or calling
    `get_order_shipment` once per order. Fetching every order's shipment here
    (concurrently — no id for the model to hallucinate, since these ids came
    from the caller's own, already-identity-filtered order list) turns that
    into one tool call the model can reason over directly.
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
        try:
            body = resp.json()
        except json.JSONDecodeError:
            return "Could not look up your orders (bad response from service)."

        orders = body.get("data", [])
        summaries = await asyncio.gather(
            *(
                _shipment_summary(client, order["id"], ctx.principal.user_id)
                for order in orders
            )
        )
        for order, summary in zip(orders, summaries, strict=True):
            order.update(summary)
        body["data"] = orders
        return json.dumps(body, ensure_ascii=False)

    return Tool(
        name="get_my_orders",
        progress_label="Getting your orders",
        description=(
            "List the current customer's own BNPL orders — status, items, plan, "
            "amounts, and shipment status for each (shipmentStatus, shippedAt, "
            "estimatedDelivery). Use this for 'what's the status of my orders?' "
            "or 'my order hasn't arrived and I don't know which one' style "
            "questions where the customer doesn't give a specific order id (use "
            "get_order instead when they do) — check shipmentStatus/"
            "estimatedDelivery yourself to spot the delayed one instead of "
            "listing every order and asking the customer to pick. Amounts are "
            "in cents — divide by 100 for the currency value."
        ),
        input_schema={"type": "object", "properties": {}},
        fn=get_my_orders,
        requires_identity=True,
    )
