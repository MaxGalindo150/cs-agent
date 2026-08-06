"""Merchant order tools — list, detail, installments, cancellation.

Order numbers in the merchant domain are **9-digit numeric** (e.g. 197688580),
unlike the buyer BNPL domain which uses prefixed ids like 'ord_0001'.

Cancellation rules (enforced by the mock server, surfaced by these tools):
- ADMIN: cancels without restriction.
- MANAGER (Gerente): needs security code + same-day order only.
- CASHIER: cannot cancel at all.
"""

from __future__ import annotations

import httpx

from agent.tools.context import ToolContext
from agent.tools.implementations.merchant._responses import decode_object, is_path_id
from agent.tools.registry import Tool


def _merchant_id(ctx: ToolContext) -> str:
    assert ctx.principal is not None
    return ctx.principal.merchant_id or ""


async def _owned_order(
    client: httpx.AsyncClient, ctx: ToolContext, order_number: str
) -> tuple[httpx.Response | None, str | None]:
    if not is_path_id(order_number):
        return None, f"No order found with number '{order_number}'."
    try:
        response = await client.get(f"/api/v1/orders/{order_number}")
    except httpx.RequestError:
        return None, "The order service is unavailable right now — try again shortly."
    if response.status_code == 404:
        return None, f"No order found with number '{order_number}'."
    if response.status_code != 200:
        return None, (
            f"Could not look up order '{order_number}' (status {response.status_code})."
        )
    body = decode_object(response)
    if body is None or str(body.get("merchantId")) != _merchant_id(ctx):
        # Deliberately indistinguishable from a missing order: never disclose
        # whether another merchant owns a supplied number.
        return None, f"No order found with number '{order_number}'."
    return response, None


def make_list_merchant_orders_tool(client: httpx.AsyncClient) -> Tool:
    async def list_merchant_orders(
        ctx: ToolContext,
        status: str = "",
        channel: str = "",
        from_date: str = "",
        to_date: str = "",
    ) -> str:
        mid = _merchant_id(ctx)
        if not mid:
            return "No merchant is identified for this conversation."
        params: dict[str, str] = {"merchantId": mid}
        if status:
            params["status"] = status
        if channel:
            params["channel"] = channel
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        try:
            resp = await client.get("/api/v1/orders", params=params)
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return f"Could not look up orders (status {resp.status_code})."
        return resp.text

    return Tool(
        name="list_merchant_orders",
        progress_label="Listing merchant orders",
        description=(
            "List orders for a merchant (aliado), with optional filters: "
            "status, channel, date range. Use this when the merchant asks "
            "about their sales, recent orders, or orders with a specific "
            "status. Order numbers in results are 9-digit numbers. Amounts "
            "are in cents — divide by 100 for the dollar value."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: IN_PROGRESS, CLOSED, "
                    "OPEN, CANCELLED, PENDING.",
                },
                "channel": {
                    "type": "string",
                    "description": "Filter by channel: QR, LINK, OFFLINE, IN_APP.",
                },
                "from_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) for the start of the range.",
                },
                "to_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) for the end of the range.",
                },
            },
        },
        fn=list_merchant_orders,
        requires_identity=True,
    )


def make_get_order_detail_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order_detail(ctx: ToolContext, order_number: str = "") -> str:
        assert ctx.principal is not None
        if not order_number:
            return (
                "get_order_detail needs an order_number (9-digit number, "
                "e.g. '197688580'). Call it again with one."
            )
        resp, error = await _owned_order(client, ctx, order_number)
        if error is not None:
            return error
        assert resp is not None
        return resp.text

    return Tool(
        name="get_order_detail",
        progress_label="Getting order {order_number}",
        description=(
            "Look up a single order by its 9-digit order number (e.g. "
            "'197688580'). Returns the full order detail: status, channel, "
            "products, buyer info, amounts (down payment, financed, total), "
            "invoice info, shipment status, and discount breakdown. Amounts "
            "are in cents — divide by 100 for the dollar value."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "The 9-digit order number, e.g. '197688580'.",
                }
            },
            "required": ["order_number"],
        },
        fn=get_order_detail,
        requires_identity=True,
    )


def make_get_order_installments_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order_installments(ctx: ToolContext, order_number: str = "") -> str:
        assert ctx.principal is not None
        if not order_number:
            return (
                "get_order_installments needs an order_number (9-digit number). "
                "Call it again with one."
            )
        _, error = await _owned_order(client, ctx, order_number)
        if error is not None:
            return error
        try:
            resp = await client.get(f"/api/v1/orders/{order_number}/installments")
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if resp.status_code == 404:
            return f"No order found with number '{order_number}'."
        if resp.status_code != 200:
            return (
                f"Could not look up installments for order '{order_number}' "
                f"(status {resp.status_code})."
            )
        return resp.text

    return Tool(
        name="get_order_installments",
        progress_label="Getting installments for order {order_number}",
        description=(
            "List the payment installments for a merchant's order — "
            "installment number, amount, due date, status, and the payments "
            "applied to each (payment method, reference number, amount in VES, "
            "payment status: VERIFIED/CANCELLED/PENDING/RETURNED). Use this "
            "to answer 'did the down payment go through?' or 'why isn't the "
            "initial reflected?'. Amounts are in cents — divide by 100."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "The 9-digit order number.",
                }
            },
            "required": ["order_number"],
        },
        fn=get_order_installments,
        requires_identity=True,
    )


def make_cancel_order_tool(client: httpx.AsyncClient) -> Tool:
    async def cancel_order(
        ctx: ToolContext,
        order_number: str = "",
        reason_id: int = 0,
        security_code: str = "",
    ) -> str:
        assert ctx.principal is not None
        employee_id = ctx.principal.employee_id or ""
        if not employee_id:
            return "Cancelling an order requires an employee identified by the portal."
        if not order_number:
            return "cancel_order needs an order_number."
        if reason_id <= 0:
            return "cancel_order needs a valid reason_id."
        _, error = await _owned_order(client, ctx, order_number)
        if error is not None:
            return error
        payload: dict[str, str | int] = {
            "employeeId": employee_id,
            "reasonId": reason_id,
        }
        if security_code:
            payload["securityCode"] = security_code
        try:
            response = await client.post(
                f"/api/v1/orders/{order_number}/cancel", json=payload
            )
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if response.status_code != 200:
            body = decode_object(response) or {}
            message = body.get("message") or body.get("error") or "Cancellation failed"
            return f"Could not cancel order: {message}"
        return response.text

    return Tool(
        name="cancel_order",
        progress_label="Cancelling order {order_number}",
        description=(
            "Cancel an order owned by the authenticated merchant. The portal must "
            "also identify the employee: ADMIN can cancel eligible orders; MANAGER "
            "needs a six-digit security code and can only cancel same-day orders; "
            "CASHIER cannot cancel. Call get_cancellation_reasons first and only "
            "execute after the merchant explicitly confirms the action."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "The 9-digit order number.",
                },
                "reason_id": {
                    "type": "integer",
                    "description": "A valid id from get_cancellation_reasons.",
                },
                "security_code": {
                    "type": "string",
                    "description": "Six-digit manager code; omit for ADMIN.",
                },
            },
            "required": ["order_number", "reason_id"],
        },
        fn=cancel_order,
        requires_identity=True,
    )


def make_get_cancellation_reasons_tool(client: httpx.AsyncClient) -> Tool:
    async def get_cancellation_reasons(ctx: ToolContext) -> str:
        assert ctx.principal is not None
        employee_id = ctx.principal.employee_id or ""
        if not employee_id:
            return (
                "Viewing cancellation reasons requires an employee identified "
                "by the portal."
            )
        if not is_path_id(employee_id):
            return f"No employee found with id '{employee_id}'."
        try:
            employee_response = await client.get(f"/api/v1/employees/{employee_id}")
            employee = (
                decode_object(employee_response)
                if employee_response.status_code == 200
                else None
            )
            if employee is None or str(employee.get("merchantId")) != (
                ctx.principal.merchant_id or ""
            ):
                return f"No employee found with id '{employee_id}'."
            resp = await client.get(
                "/api/v1/orders/cancellation-reasons",
                params={"role": str(employee.get("role", ""))},
            )
        except httpx.RequestError:
            return "The order service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return (
                f"Could not look up cancellation reasons (status {resp.status_code})."
            )
        return resp.text

    return Tool(
        name="get_cancellation_reasons",
        progress_label="Getting cancellation reasons",
        description=(
            "List the valid cancellation reasons for an order. Each reason "
            "has an id and a label (e.g. 'customer_request', 'fraud_suspect'). "
            "You need a reason id to cancel an order. Call this before "
            "attempting a cancellation so you can present valid reasons to "
            "the merchant."
        ),
        input_schema={"type": "object", "properties": {}},
        fn=get_cancellation_reasons,
        requires_identity=True,
    )
