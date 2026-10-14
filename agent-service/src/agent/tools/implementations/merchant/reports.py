"""Aliado monthly settlement report — "what does Cashea pay me this month?"

``GET /v2/reports?view=summarized`` for one calendar month, with the aliado's
own token (the portal shows it to admins; the backend enforces that). Values
arrive as strings, in dollars. ``final_compensation`` is the bottom line:
positive means Cashea pays the aliado, negative means the aliado owes Cashea
(merchant-web's MonthlyReportApiKeys.ts).

Shape taken from merchant-web's DTOs; not yet seen with real data — the
staging account used so far has no reports.
"""

from __future__ import annotations

import calendar
import json
import re
from typing import Any

import httpx

from agent.tools.context import ToolContext
from agent.tools.implementations.merchant._http import Found, merchant_get
from agent.tools.registry import Tool

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


def make_get_monthly_report_tool(client: httpx.AsyncClient) -> Tool:
    async def get_monthly_report(ctx: ToolContext, month: str = "") -> str:
        match = _MONTH.match(month.strip())
        if not match or not 1 <= int(match.group(2)) <= 12:
            return "month must be YYYY-MM, e.g. '2026-09'."
        year, mon = int(match.group(1)), int(match.group(2))
        last_day = calendar.monthrange(year, mon)[1]
        params = [
            ("date_from", f"{year:04d}-{mon:02d}-01"),
            ("date_to", f"{year:04d}-{mon:02d}-{last_day:02d}"),
            ("view", "summarized"),
        ]
        result = await merchant_get(client, ctx, "/v2/reports", params)
        if result is None:
            return f"No settlement report for {month}."
        if not isinstance(result, Found):
            return result
        reports = result.data.get("reports") or []
        if not reports:
            return (
                f"No settlement report for {month} yet — reports appear once "
                "Cashea closes the period."
            )
        return json.dumps(
            {"month": month, "reports": [_report(r) for r in reports]},
            ensure_ascii=False,
        )

    return Tool(
        name="get_monthly_report",
        progress_label="Consultando el reporte de {month}",
        description=(
            "The aliado's settlement report for one calendar month: total "
            "sales, Cashea's service fee and taxes, installments recognised, "
            "payment errors, adjustments, and final_compensation — positive "
            "means Cashea pays the aliado that amount, negative means the "
            "aliado owes Cashea. Values are in dollars."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "The month, YYYY-MM."}
            },
            "required": ["month"],
        },
        fn=get_monthly_report,
        requires_identity=True,
        audiences=frozenset({"merchant"}),
    )


def _report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": report.get("date_from"),
        "to": report.get("date_to"),
        "lines": [
            {
                "key": line.get("key"),
                "name": line.get("name"),
                "value": line.get("value"),
            }
            for line in report.get("lines") or []
        ],
        "adjustments": [
            {"name": a.get("name"), "value": a.get("value"), "type": a.get("type")}
            for a in report.get("adjustments") or []
        ],
    }
