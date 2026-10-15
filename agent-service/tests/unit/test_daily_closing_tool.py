"""Unit tests for get_daily_closing (agent/tools/implementations/merchant/).

The merchant API is an httpx.MockTransport. Under test: it reads only the
employee's own store, with their token; what it returns; and that today's
closing is recognised in Venezuelan time.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx

from agent.identity import Principal
from agent.tools.context import ToolContext
from agent.tools.implementations.merchant._http import TOO_SLOW
from agent.tools.implementations.merchant.daily_closing import (
    make_get_daily_closing_tool,
)

_STORE = "69190d7f-b2e1-471f-9fd4-80a4071e3688"
_ALIADO = ToolContext(
    principal=Principal(
        user_id="uid-1", merchant_id="42", store_uuid=_STORE, store_name="Centro"
    ),
    host_credential="aliado-firebase-token",
)
_TODAY = {
    "ordersCount": 3,
    "totalChargedAmount": 150,
    "totalFinancedAmount": 90,
    "conciliationsByPos": [
        {
            "pos": {"name": "Caja 1", "uuid": "p1"},
            "ordersCount": 3,
            "totalChargedAmount": 150,
            "totalFinancedAmount": 90,
        }
    ],
}


def _client(
    last: dict[str, str] | None, seen: list[httpx.Request]
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/last"):
            return httpx.Response(200, json=last) if last else httpx.Response(404)
        return httpx.Response(200, json=_TODAY)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://merchant-api"
    )


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def test_reads_the_own_store_with_the_aliados_token() -> None:
    seen: list[httpx.Request] = []
    last = {"createdAt": "2026-08-25T19:30:57.205Z"}

    out = json.loads(
        await make_get_daily_closing_tool(_client(last, seen)).fn(ctx=_ALIADO)
    )

    assert sorted(r.url.path for r in seen) == [
        f"/stores/v2/{_STORE}/dailyConciliation",
        f"/stores/v2/{_STORE}/dailyConciliation/last",
    ]
    assert all(
        r.headers["Authorization"] == "Bearer aliado-firebase-token" for r in seen
    )
    assert out == {
        "store": "Centro",
        "today_so_far": {
            "orders": 3,
            "total_facturado": 150,
            "total_financiado_por_cashea": 90,
        },
        "by_caja": [
            {
                "caja": "Caja 1",
                "orders": 3,
                "total_facturado": 150,
                "total_financiado_por_cashea": 90,
            }
        ],
        "last_closing_at": "2026-08-25 15:30 (hora de Venezuela)",
        "closed_today": False,
    }


async def test_a_closing_earlier_today_counts_as_today() -> None:
    a_minute_ago = datetime.now(UTC) - timedelta(minutes=1)
    last = {"createdAt": _iso(a_minute_ago)}

    out = json.loads(
        await make_get_daily_closing_tool(_client(last, [])).fn(ctx=_ALIADO)
    )

    assert out["closed_today"] is True


async def test_a_store_that_never_closed() -> None:
    out = json.loads(
        await make_get_daily_closing_tool(_client(None, [])).fn(ctx=_ALIADO)
    )

    assert out["last_closing_at"] is None
    assert out["closed_today"] is None


async def test_without_an_assigned_store_nothing_is_called() -> None:
    seen: list[httpx.Request] = []
    no_store = ToolContext(
        principal=Principal(user_id="uid-1", merchant_id="42"),
        host_credential="aliado-firebase-token",
    )

    out = await make_get_daily_closing_tool(_client(None, seen)).fn(ctx=no_store)

    assert "no store assigned" in out
    assert seen == []


async def test_a_slow_answer_is_reported_as_slow() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://merchant-api"
    )

    out = await make_get_daily_closing_tool(client).fn(ctx=_ALIADO)

    assert out == TOO_SLOW
