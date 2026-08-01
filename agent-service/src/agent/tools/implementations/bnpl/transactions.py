"""BNPL transaction tools — read-only lookups against the external BNPL system.

Same shape as `orders.py`: a `make_*_tool` factory bound to a shared
`httpx.AsyncClient`, testable with a mock transport.

Identity-gated (`requires_identity=True`, docs/SECURITY.md §3), but unlike
`get_order`, there is no id to check ownership against — the caller's own
`userId` is the only filter this tool can ever apply, taken solely from
`ctx.principal` (the same "no id for the model to hallucinate" shape as
`get_my_orders`).
"""

from __future__ import annotations

import json

import httpx

from agent.tools.context import ToolContext
from agent.tools.registry import Tool

_TXN_TYPES = (
    "purchase",
    "payment",
    "refund",
    "fee",
    "interest",
    "points_earned",
    "points_redeemed",
    "adjustment",
)


def make_get_transactions_tool(client: httpx.AsyncClient) -> Tool:
    async def get_transactions(ctx: ToolContext, type: str = "") -> str:
        assert ctx.principal is not None  # guaranteed by requires_identity
        params = {"userId": ctx.principal.user_id}
        if type:
            params["type"] = type
        try:
            resp = await client.get("/api/v1/transactions", params=params)
        except httpx.RequestError:
            return (
                "The transactions service is unavailable right now — try again shortly."
            )
        if resp.status_code != 200:
            return f"Could not look up your transactions (status {resp.status_code})."
        try:
            body = resp.json()
        except json.JSONDecodeError:
            return "Could not look up your transactions (bad response from service)."
        # resp.json() can decode to any JSON type, not just an object — a
        # bare list/string/number/null would make body.get() below raise
        # AttributeError, uncaught by the JSONDecodeError guard above.
        if not isinstance(body, dict):
            return "Could not look up your transactions (bad response from service)."
        transactions = body.get("data")
        # Never trust the upstream userId filter alone — verify every
        # transaction actually belongs to the caller before returning any of
        # them. Unlike get_my_orders' best-effort shipment enrichment, a
        # transaction failing this check means the filter itself may be
        # broken, so the whole response is refused rather than silently
        # narrowed to a partial list.
        if not isinstance(transactions, list) or any(
            not isinstance(txn, dict) or txn.get("userId") != ctx.principal.user_id
            for txn in transactions
        ):
            return "Could not look up your transactions (bad response from service)."
        return json.dumps(body, ensure_ascii=False)

    return Tool(
        name="get_transactions",
        progress_label="Getting your transactions",
        description=(
            "List the current customer's own account transactions — purchases, "
            "payments, refunds, fees, interest, and points — most recent first. "
            "Use this to check whether a payment actually went through, spot a "
            "duplicate or failed charge, or review the full transaction history. "
            "Amounts are in cents — divide by 100 for the currency value."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": list(_TXN_TYPES),
                    "description": (
                        "Optional: only return transactions of this type "
                        "(e.g. 'payment' to check for a duplicate or failed charge)."
                    ),
                }
            },
        },
        fn=get_transactions,
        requires_identity=True,
    )
