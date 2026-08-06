"""Merchant finance tools — payouts, invoices, monthly reports, daily conciliation.

These are the #1 support topics for aliados:
- "No he recibido la transferencia del periodo X" → ``get_payouts``
- "No me llegaron las facturas de enero a mayo" → ``get_invoices``
- "Cuánto me deben del mes?" → ``get_monthly_report``
- "La conciliación de ayer no cuadra" → ``get_daily_conciliation``
"""

from __future__ import annotations

import httpx

from agent.tools.context import ToolContext
from agent.tools.registry import Tool


def make_get_payouts_tool(client: httpx.AsyncClient) -> Tool:
    async def get_payouts(
        ctx: ToolContext,
        from_date: str = "",
        to_date: str = "",
    ) -> str:
        assert ctx.principal is not None
        mid = ctx.principal.merchant_id or ""
        if not mid:
            return "No merchant is identified for this conversation."
        params: dict[str, str] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        try:
            resp = await client.get(f"/api/v1/merchants/{mid}/payouts", params=params)
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return f"Could not look up payouts (status {resp.status_code})."
        return resp.text

    return Tool(
        name="get_payouts",
        progress_label="Getting merchant payouts",
        description=(
            "List Cashea's payouts (bank transfers) to a merchant, optionally "
            "filtered by date range. Each payout covers a period and includes "
            "grossAmount, serviceFee, retentions, adjustments, netAmount, "
            "status (PENDING/SENT/FAILED), sentAt, bankReference, and "
            "bankAccountLast4. Use this for 'no he recibido la transferencia' "
            "or 'cuándo me depositaron'. Amounts are in cents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "from_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) start of range.",
                },
                "to_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) end of range.",
                },
            },
        },
        fn=get_payouts,
        requires_identity=True,
    )


def make_get_invoices_tool(client: httpx.AsyncClient) -> Tool:
    async def get_invoices(
        ctx: ToolContext,
        from_date: str = "",
        to_date: str = "",
        status: str = "",
    ) -> str:
        assert ctx.principal is not None
        mid = ctx.principal.merchant_id or ""
        if not mid:
            return "No merchant is identified for this conversation."
        params: dict[str, str] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if status:
            params["status"] = status
        try:
            resp = await client.get(f"/api/v1/merchants/{mid}/invoices", params=params)
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return f"Could not look up invoices (status {resp.status_code})."
        return resp.text

    return Tool(
        name="get_invoices",
        progress_label="Getting merchant invoices",
        description=(
            "List Cashea's invoices to a merchant for technological services, "
            "optionally filtered by date range and status (ISSUED, SENT, "
            "NOT_SENT). Each invoice has a period, number, amount, iva, "
            "isrlRetained, status, sentToEmail, and sentAt. Use this for "
            "'no me llegaron las facturas' — filter by status=NOT_SENT to "
            "find undelivered ones. Amounts are in cents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "from_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) start of range.",
                },
                "to_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) end of range.",
                },
                "status": {
                    "type": "string",
                    "description": "Filter: ISSUED, SENT, NOT_SENT.",
                },
            },
        },
        fn=get_invoices,
        requires_identity=True,
    )


def make_get_monthly_report_tool(client: httpx.AsyncClient) -> Tool:
    async def get_monthly_report(
        ctx: ToolContext,
        period: str = "",
    ) -> str:
        assert ctx.principal is not None
        mid = ctx.principal.merchant_id or ""
        if not mid:
            return "No merchant is identified for this conversation."
        # If a specific period is requested, fetch the detail for that period.
        path = f"/api/v1/merchants/{mid}/monthly-reports"
        if period:
            path = f"{path}/{period}"
        try:
            resp = await client.get(path)
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return f"Could not look up monthly reports (status {resp.status_code})."
        return resp.text

    return Tool(
        name="get_monthly_report",
        progress_label="Getting monthly report {period}",
        description=(
            "Get monthly reports for a merchant. Without a 'period', lists "
            "available periods (each with compensation, payment timeline, "
            "missed installments, service fee, errors and adjustments). "
            "With a 'period' (e.g. '2025-07'), returns that specific period's "
            "full report. Use this for 'cuánto me deben del mes' or "
            "'el reporte de julio está mal'. Amounts are in cents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Specific period in YYYY-MM format. "
                    "Omit to list all available periods.",
                },
            },
        },
        fn=get_monthly_report,
        requires_identity=True,
    )


def make_get_daily_conciliation_tool(client: httpx.AsyncClient) -> Tool:
    async def get_daily_conciliation(
        ctx: ToolContext,
        store_uuid: str = "",
        date: str = "",
        view: str = "",
    ) -> str:
        assert ctx.principal is not None
        suid = store_uuid or ctx.principal.store_uuid or ""
        if not suid:
            return (
                "get_daily_conciliation needs a store_uuid. Either pass one "
                "explicitly or ensure the conversation has a store identified."
            )
        try:
            store_response = await client.get(f"/api/v1/stores/{suid}")
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        store = store_response.json() if store_response.status_code == 200 else None
        if not isinstance(store, dict) or str(store.get("merchantId")) != (
            ctx.principal.merchant_id or ""
        ):
            return f"No store found with id '{suid}'."
        path = f"/api/v1/stores/{suid}/daily-conciliation"
        params: dict[str, str] = {}
        if date:
            params["date"] = date
        # Optional sub-resource: /last or /history
        if view in ("last", "history"):
            path = f"{path}/{view}"
        try:
            resp = await client.get(path, params=params or None)
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if resp.status_code != 200:
            return f"Could not look up daily conciliation (status {resp.status_code})."
        return resp.text

    return Tool(
        name="get_daily_conciliation",
        progress_label="Getting daily conciliation for store {store_uuid}",
        description=(
            "Get the daily conciliation for a store — the per-POS breakdown of "
            "orders and amounts charged/financed for a given day. Use 'date' "
            "(YYYY-MM-DD) to specify the day; omit for today. Use view='last' "
            "for the most recent conciliation, view='history' for the list. "
            "Use this for 'la conciliación de ayer no cuadra' or 'cuántas "
            "ventas hicimos ayer'. Amounts are in cents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "store_uuid": {
                    "type": "string",
                    "description": "The store UUID.",
                },
                "date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Omit for today.",
                },
                "view": {
                    "type": "string",
                    "description": "'last' for most recent, 'history' for list, "
                    "omit for a specific date.",
                },
            },
        },
        fn=get_daily_conciliation,
        requires_identity=True,
    )
