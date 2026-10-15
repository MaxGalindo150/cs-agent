"""Aliado order tools: find their store's orders and read one in detail.

``GET /v2/orders`` and ``GET /v2/orders/{uuid}`` on Cashea's merchant API,
with the aliado's own token — the backend returns only their merchant's
orders, so there's no ownership check to do here (contrast the consumer tools
in ../bnpl/orders.py, which check ``userId`` themselves).

Arguments are validated before anything is sent: the model builds them, and
the uuid ends up in a URL path. Amounts come back in dollars.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from agent import clock
from agent.tools.context import ToolContext
from agent.tools.implementations.merchant._http import Found, merchant_get
from agent.tools.registry import Tool

STATUSES = ("OPEN", "IN_PROGRESS", "CLOSED", "CANCELLED", "PENDING")
# How the portal names each status (merchant-web OrderStatusMapper.ts), and
# what it means — so the agent says "Pagada", never "CLOSED" or "Open".
_STATUS_LABELS = {
    "OPEN": "Abierta: esperando que el comprador la confirme en su app",
    "PENDING": "Pendiente: el comprador confirmó, falta el pago inicial",
    "IN_PROGRESS": "En progreso: inicial pagada, el comprador paga sus cuotas",
    "CLOSED": "Pagada",
    "CANCELLED": "Cancelada",
}
# Channel and delivery names as the portal shows them (displayChannelValue,
# OrderShipmentStatusMapper.ts).
_CHANNEL_LABELS = {
    "IN_STORE": "QR",
    "REMOTE": "Link",
    "OFFLINE": "Sin Conexión",
    "IN_APP": "Online",
    "WEB_CHECKOUT": "Checkout Web",
}
_DELIVERY_LABELS = {
    "DELIVERED": "Entregado",
    "TO_DELIVER": "Pendiente de entrega",
    "PENDING": "Pendiente",
    "IN_TRANSIT": "En tránsito",
    "RETURNED": "Devuelto",
    "CANCELLED": "Cancelada",
}
# Installment statuses as the portal's payment plan shows them
# (merchant-web OrderDetails.helper.ts / InstallmentStatus.ts).
_INSTALLMENT_LABELS = {
    "SCHEDULED": "Agendada",
    "DONE": "Pagada",
    "PENDING": "En verificación: pago registrado, Cashea lo revisa",
    "DELAYED": "Atrasada",
    "GRACED": "En período de gracia",
    "RENEGOTIATED": "Renegociada",
    "CANCELLED": "Cancelada",
}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_MAX_RESULTS = 10


def make_search_orders_tool(client: httpx.AsyncClient) -> Tool:
    async def search_orders(
        ctx: ToolContext,
        order_number: str = "",
        buyer_id_number: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 5,
    ) -> str:
        params: list[tuple[str, str]] = [("page", "1"), ("sorting", "createdAt_desc")]
        if order_number:
            if not order_number.strip().isdigit():
                return "order_number must be digits only, e.g. '123456'."
            params.append(("orderNumber", order_number.strip()))
        if buyer_id_number:
            params.append(("identificationNumber", buyer_id_number.strip()))
        if status:
            if status not in STATUSES:
                return f"status must be one of: {', '.join(STATUSES)}."
            params.append(("status", status))
        for name, value, param in (
            ("date_from", date_from, "from"),
            ("date_to", date_to, "to"),
        ):
            if value:
                if not _DATE.match(value):
                    return f"{name} must be a date as YYYY-MM-DD."
                params.append((param, value))
        params.append(("limit", str(max(1, min(int(limit), _MAX_RESULTS)))))

        result = await merchant_get(client, ctx, "/v2/orders", params)
        if not isinstance(result, Found):
            return result or "No orders found."
        rows = result.data.get("data") or []
        if not rows:
            return "No orders match those filters."
        return json.dumps(
            {
                "orders": [_summary(row) for row in rows],
                "more_available": bool(
                    (result.data.get("pagination") or {}).get("hasMore")
                ),
            },
            ensure_ascii=False,
        )

    return Tool(
        name="search_orders",
        progress_label="Buscando órdenes",
        description=(
            "Find orders of the aliado's store, newest first. Filter by order "
            "number, the buyer's ID number (cédula), status, and/or a creation "
            "date range; with no filters it lists the latest orders. Returns "
            "each order's order_uuid (needed for get_order_detail), number, "
            "date, amount in dollars, status and store."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "Order number, digits only.",
                },
                "buyer_id_number": {
                    "type": "string",
                    "description": "The buyer's ID number (cédula).",
                },
                "status": {"type": "string", "enum": list(STATUSES)},
                "date_from": {
                    "type": "string",
                    "description": "Created on or after, YYYY-MM-DD.",
                },
                "date_to": {
                    "type": "string",
                    "description": "Created on or before, YYYY-MM-DD.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_RESULTS},
            },
        },
        fn=search_orders,
        requires_identity=True,
        audiences=frozenset({"merchant"}),
    )


def make_get_order_detail_tool(client: httpx.AsyncClient) -> Tool:
    async def get_order_detail(ctx: ToolContext, order_uuid: str = "") -> str:
        if not _UUID.match(order_uuid.strip()):
            return (
                "get_order_detail needs the order_uuid from search_orders "
                "(a UUID). Find the order with search_orders first."
            )
        result = await merchant_get(client, ctx, f"/v2/orders/{order_uuid.strip()}")
        if result is None:
            return "No order found with that id in this store."
        if not isinstance(result, Found):
            return result
        return json.dumps(_detail(result.data), ensure_ascii=False)

    return Tool(
        name="get_order_detail",
        progress_label="Consultando la orden",
        description=(
            "Read one order of the aliado's store in full, by the order_uuid "
            "from search_orders: status, amounts in dollars (total, down "
            "payment, financed), whether Cashea already paid the store for it, "
            "installments, products, cancellation and shipment status, and "
            "the buyer's name and ID number."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "order_uuid": {
                    "type": "string",
                    "description": "The order_uuid from search_orders.",
                }
            },
            "required": ["order_uuid"],
        },
        fn=get_order_detail,
        requires_identity=True,
        audiences=frozenset({"merchant"}),
    )


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_uuid": row.get("orderUuid"),
        "order_number": row.get("orderNumber"),
        "created_at": clock.describe(row.get("createdAt")),
        "amount": row.get("amount"),
        "status": _label(_STATUS_LABELS, row.get("statusName")),
        "store": row.get("storeName"),
        "channel": _label(_CHANNEL_LABELS, row.get("channel")),
        "delivery_status": _delivery(row.get("statusName"), row.get("deliveryStatus")),
    }


def _detail(order: dict[str, Any]) -> dict[str, Any]:
    """An allowlist, not a blocklist: a new field the backend adds (say, a
    buyer's address) stays out until someone decides it belongs here."""
    status = order.get("status")
    status_code = (
        status.get("name") if isinstance(status, dict) else order.get("statusName")
    )
    payment = order.get("paymentDetails") or {}
    buyer = payment.get("user") or {}
    cancellation = order.get("cancellationData") or {}
    shipment = order.get("shipment") or {}
    return {
        "order_number": order.get("identifierNumber"),
        "created_at": clock.describe(order.get("createdAt")),
        "status": _label(_STATUS_LABELS, status_code),
        "amount": order.get("amount"),
        "down_payment_amount": order.get("downPaymentAmount"),
        "financed_amount": order.get("financedAmount"),
        "down_payment_paid_at": clock.describe(order.get("downPaymentPaidAt")),
        "paid_to_merchant": order.get("paidToMerchant"),
        "channel": _label(_CHANNEL_LABELS, order.get("channel")),
        "delivery_status": _delivery(status_code, order.get("deliveryStatus")),
        "store": (order.get("store") or {}).get("name"),
        "seller": (order.get("employee") or {}).get("fullName"),
        "buyer": {
            "name": buyer.get("fullName"),
            "id_number": buyer.get("identificationNumber"),
        },
        "installments": [
            {
                "number": i.get("installmentNumber"),
                "amount": i.get("amount"),
                "status": _label(_INSTALLMENT_LABELS, i.get("status")),
                "due_date": i.get("scheduledPaymentDate"),
            }
            for i in (payment.get("installments") or [])
        ],
        "products": [
            {
                "name": p.get("name"),
                "quantity": p.get("quantity"),
                "price": p.get("price"),
            }
            for p in (order.get("orderProducts") or [])
        ],
        "cancellation": {
            "reason": cancellation.get("cancellationReason"),
            "cancelled_by": cancellation.get("cancelledBy"),
        }
        if cancellation
        else None,
        "shipment_status": shipment.get("status") if shipment else None,
    }


def _label(labels: dict[str, str], code: Any) -> Any:
    """The portal's name for a status code; an unknown code passes through
    as-is rather than being hidden."""
    return labels.get(code, code) if isinstance(code, str) else code


def _delivery(status_code: Any, delivery: Any) -> Any:
    """Like the portal's Entrega column: a delivery state only means
    something once the buyer has taken the order."""
    if status_code == "OPEN":
        return "No aplica"
    if status_code == "CANCELLED":
        return "Orden cancelada"
    return _label(_DELIVERY_LABELS, delivery)
