"""Unit tests for the aliado tools (agent/tools/implementations/merchant/).

Cashea's merchant API is an httpx.MockTransport: no network. Under test: what
each tool sends (path, filters, the aliado's own token), what it lets through
to the model (an allowlist — never a buyer's contact details), and how every
failure becomes honest text.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from agent.identity import Principal
from agent.tools.context import ToolContext
from agent.tools.implementations.merchant._http import NO_ACCESS, NO_CREDENTIAL
from agent.tools.implementations.merchant.orders import (
    make_get_order_detail_tool,
    make_search_orders_tool,
)
from agent.tools.implementations.merchant.reports import make_get_monthly_report_tool

_UUID = "9b2f0c1e-3a4d-4e5f-8a9b-0c1d2e3f4a5b"
_ALIADO = ToolContext(
    principal=Principal(user_id="uid-1", merchant_id="42"),
    host_credential="aliado-firebase-token",
)


class _Api:
    """Records requests; answers each with ``respond(request)``."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self._respond(request)

        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://merchant-api"
        )


def _ok(body: Any) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: httpx.Response(200, json=body)


_ROW = {
    "orderUuid": _UUID,
    "orderNumber": 123456,
    "createdAt": "2026-10-14T15:00:00Z",
    "amount": 50,
    "statusName": "OPEN",
    "storeName": "Centro",
    "channel": "IN_STORE",
    "deliveryStatus": "DELIVERED",
    "posName": "Caja 1",
}


# --- search_orders -----------------------------------------------------------


async def test_search_sends_the_filters_and_the_aliados_token() -> None:
    api = _Api(_ok({"data": [_ROW], "pagination": {"hasMore": True}}))
    tool = make_search_orders_tool(api.client())

    out = json.loads(
        await tool.fn(
            ctx=_ALIADO,
            order_number="123456",
            buyer_id_number="V12345678",
            status="OPEN",
            date_from="2026-10-01",
            date_to="2026-10-14",
            limit=50,
        )
    )

    request = api.requests[0]
    assert request.url.path == "/v2/orders"
    assert request.headers["Authorization"] == "Bearer aliado-firebase-token"
    params = dict(request.url.params)
    assert params == {
        "page": "1",
        "sorting": "createdAt_desc",
        "orderNumber": "123456",
        "identificationNumber": "V12345678",
        "status": "OPEN",
        "from": "2026-10-01",
        "to": "2026-10-14",
        "limit": "10",  # capped
    }
    assert out["more_available"] is True
    assert out["orders"] == [
        {
            "order_uuid": _UUID,
            "order_number": 123456,
            "created_at": "2026-10-14T15:00:00Z",
            "amount": 50,
            "status": "Abierta: esperando que el comprador la confirme en su app",
            "store": "Centro",
            "channel": "IN_STORE",
            "delivery_status": "DELIVERED",
        }
    ]


@pytest.mark.parametrize(
    ("kwargs", "complaint"),
    [
        ({"order_number": "12a"}, "digits"),
        ({"status": "PAID"}, "status must be one of"),
        ({"date_from": "14/10/2026"}, "YYYY-MM-DD"),
    ],
)
async def test_search_rejects_bad_filters_without_calling(
    kwargs: dict[str, str], complaint: str
) -> None:
    api = _Api(_ok({"data": []}))

    out = await make_search_orders_tool(api.client()).fn(ctx=_ALIADO, **kwargs)

    assert complaint in out
    assert api.requests == []


async def test_search_with_no_matches_says_so() -> None:
    api = _Api(_ok({"data": [], "pagination": {"hasMore": False}}))

    out = await make_search_orders_tool(api.client()).fn(ctx=_ALIADO)

    assert out == "No orders match those filters."


# --- get_order_detail --------------------------------------------------------

_DETAIL = {
    "id": "924986",  # internal; the order number is identifierNumber
    "identifierNumber": 123456,
    "uuid": _UUID,
    "createdAt": "2026-10-14T15:00:00Z",
    "amount": 50,
    "downPaymentAmount": 10,
    "financedAmount": 40,
    "paidToMerchant": False,
    "status": {"id": 3, "name": "OPEN", "displayName": "Open"},
    "store": {"id": 7, "name": "Centro"},
    "employee": {"fullName": "Ana Cajera"},
    "paymentDetails": {
        "user": {
            "fullName": "María Pérez",
            "identificationNumber": "V12345678",
            "phoneNumber": "+58 412 0000000",
            "email": "maria@example.com",
        },
        "installments": [
            {
                "id": "i1",
                "installmentNumber": 1,
                "amount": 20,
                "status": "PENDING",
                "scheduledPaymentDate": "2026-10-28",
            }
        ],
    },
    "orderProducts": [{"productId": 1, "name": "Zapatos", "quantity": 1, "price": 50}],
    "cancellationData": None,
    "shipment": {
        "status": "IN_TRANSIT",
        "userAddress": {"firstName": "María", "street": "Av. Siempre Viva 742"},
    },
}


async def test_detail_lets_through_only_the_allowlisted_fields() -> None:
    api = _Api(_ok(_DETAIL))

    raw = await make_get_order_detail_tool(api.client()).fn(
        ctx=_ALIADO, order_uuid=_UUID
    )
    out = json.loads(raw)

    assert api.requests[0].url.path == f"/v2/orders/{_UUID}"
    assert out["order_number"] == 123456
    assert out["status"].startswith("Abierta")
    assert out["paid_to_merchant"] is False
    assert out["buyer"] == {"name": "María Pérez", "id_number": "V12345678"}
    assert out["installments"][0] == {
        "number": 1,
        "amount": 20,
        "status": "En verificación: pago registrado, Cashea lo revisa",
        "due_date": "2026-10-28",
    }
    assert out["shipment_status"] == "IN_TRANSIT"
    # A buyer's contact details and address never reach the model.
    for secret in ("+58 412", "maria@example.com", "Siempre Viva"):
        assert secret not in raw


@pytest.mark.parametrize("order_uuid", ["", "123456", "../employees/uid-1"])
async def test_detail_refuses_anything_but_a_uuid(order_uuid: str) -> None:
    api = _Api(_ok(_DETAIL))

    out = await make_get_order_detail_tool(api.client()).fn(
        ctx=_ALIADO, order_uuid=order_uuid
    )

    assert "search_orders" in out
    assert api.requests == []


async def test_detail_of_an_unknown_order() -> None:
    api = _Api(lambda _: httpx.Response(404, json={"message": "not found"}))

    out = await make_get_order_detail_tool(api.client()).fn(
        ctx=_ALIADO, order_uuid=_UUID
    )

    assert out == "No order found with that id in this store."


# --- get_monthly_report ------------------------------------------------------


async def test_report_asks_for_the_whole_month_and_returns_its_lines() -> None:
    report = {
        "date_from": "2028-02-01",
        "date_to": "2028-02-29",
        "lines": [
            {
                "id": "l1",
                "key": "final_compensation",
                "section": "compensation",
                "name": "Compensación final",
                "value": "1250.40",
            }
        ],
        "adjustments": [
            {
                "id": "a1",
                "report_id": "r1",
                "key": None,
                "name": "Ajuste",
                "value": "-10.00",
                "created_at": "2028-03-01",
                "description": "x",
                "type": "DEFAULT",
            }
        ],
    }
    api = _Api(_ok({"reports": [report]}))

    out = json.loads(
        await make_get_monthly_report_tool(api.client()).fn(
            ctx=_ALIADO, month="2028-02"
        )
    )

    assert dict(api.requests[0].url.params) == {
        "date_from": "2028-02-01",
        "date_to": "2028-02-29",  # leap year
        "view": "summarized",
    }
    assert out["reports"][0]["lines"] == [
        {"key": "final_compensation", "name": "Compensación final", "value": "1250.40"}
    ]
    assert out["reports"][0]["adjustments"] == [
        {"name": "Ajuste", "value": "-10.00", "type": "DEFAULT"}
    ]


async def test_report_for_a_month_not_closed_yet() -> None:
    api = _Api(_ok({"reports": [], "total": 0}))

    out = await make_get_monthly_report_tool(api.client()).fn(
        ctx=_ALIADO, month="2026-10"
    )

    assert "No settlement report for 2026-10 yet" in out


@pytest.mark.parametrize("month", ["", "2026-13", "octubre", "2026/09"])
async def test_report_rejects_a_bad_month_without_calling(month: str) -> None:
    api = _Api(_ok({"reports": []}))

    out = await make_get_monthly_report_tool(api.client()).fn(ctx=_ALIADO, month=month)

    assert "YYYY-MM" in out
    assert api.requests == []


# --- shared failure handling -------------------------------------------------


async def test_without_the_aliados_token_nothing_is_called() -> None:
    api = _Api(_ok({"data": [_ROW]}))
    no_token = ToolContext(principal=Principal(user_id="uid-1", merchant_id="42"))

    out = await make_search_orders_tool(api.client()).fn(ctx=no_token)

    assert out == NO_CREDENTIAL
    assert api.requests == []


@pytest.mark.parametrize("status", [401, 403])
async def test_a_role_without_access_is_told_plainly(status: int) -> None:
    api = _Api(lambda _: httpx.Response(status, json={"message": "forbidden"}))

    out = await make_get_monthly_report_tool(api.client()).fn(
        ctx=_ALIADO, month="2026-09"
    )

    assert out == NO_ACCESS


async def test_errors_never_echo_the_token() -> None:
    api = _Api(lambda _: httpx.Response(500, json={"message": "boom"}))

    out = await make_search_orders_tool(api.client()).fn(ctx=_ALIADO)

    assert "500" in out
    assert "aliado-firebase-token" not in out


async def test_an_unknown_status_passes_through() -> None:
    row = {**_ROW, "statusName": "SOMETHING_NEW"}
    api = _Api(_ok({"data": [row]}))

    out = json.loads(await make_search_orders_tool(api.client()).fn(ctx=_ALIADO))

    assert out["orders"][0]["status"] == "SOMETHING_NEW"
