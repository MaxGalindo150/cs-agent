"""Merchant tool isolation tests (MockTransport, no external services)."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from agent.identity import Principal
from agent.tools.context import ToolContext
from agent.tools.implementations.merchant.auth import (
    make_get_employee_2fa_tool,
    make_register_2fa_phone_tool,
)
from agent.tools.implementations.merchant.catalog import (
    make_list_merchant_stores_tool,
)
from agent.tools.implementations.merchant.finance import (
    make_get_daily_conciliation_tool,
    make_get_payouts_tool,
)
from agent.tools.implementations.merchant.orders import (
    make_cancel_order_tool,
    make_get_cancellation_reasons_tool,
    make_get_order_detail_tool,
    make_list_merchant_orders_tool,
)

_MERCHANT = ToolContext(
    principal=Principal(
        user_id="merchant:1",
        profile="merchant",
        merchant_id="1",
    )
)
_EMPLOYEE = ToolContext(
    principal=Principal(
        user_id="merchant:1",
        profile="merchant",
        merchant_id="1",
        employee_id="emp_1",
    )
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://merchant"
    )


def test_order_list_schema_never_exposes_merchant_id() -> None:
    tool = make_list_merchant_orders_tool(httpx.AsyncClient())

    assert "merchant_id" not in tool.input_schema["properties"]


async def test_order_list_always_uses_principal_merchant() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orders"
        assert request.url.params["merchantId"] == "1"
        return httpx.Response(200, json={"data": []})

    async with _client(handle) as client:
        output = await make_list_merchant_orders_tool(client).fn(_MERCHANT)

    assert output == '{"data":[]}'


async def test_order_detail_hides_foreign_merchant_order() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"orderNumber": "197000001", "merchantId": 2, "buyer": {}},
        )

    async with _client(handle) as client:
        output = await make_get_order_detail_tool(client).fn(
            _MERCHANT, order_number="197000001"
        )

    assert output == "No order found with number '197000001'."
    assert "buyer" not in output


async def test_payouts_always_use_principal_merchant() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/merchants/1/payouts"
        return httpx.Response(200, json={"data": []})

    tool = make_get_payouts_tool(httpx.AsyncClient())
    assert "merchant_id" not in tool.input_schema["properties"]
    async with _client(handle) as client:
        output = await make_get_payouts_tool(client).fn(_MERCHANT)

    assert output == '{"data":[]}'


async def test_conciliation_rejects_foreign_store() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/api/v1/stores/store_2"
        return httpx.Response(200, json={"uuid": "store_2", "merchantId": 2})

    async with _client(handle) as client:
        output = await make_get_daily_conciliation_tool(client).fn(
            _MERCHANT, store_uuid="store_2"
        )

    assert output == "No store found with id 'store_2'."
    assert calls == 1


async def test_employee_lookup_hides_foreign_merchant_employee() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "emp_2", "merchantId": 2})

    async with _client(handle) as client:
        output = await make_get_employee_2fa_tool(client).fn(
            _MERCHANT, employee_id="emp_2"
        )

    assert output == "No employee found with id 'emp_2'."


async def test_employee_lookup_omits_contact_details() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "emp_1",
                "merchantId": 1,
                "email": "private@example.com",
                "phoneNumber": "+58 412 123 4567",
                "phoneRegistered": True,
                "role": "MANAGER",
            },
        )

    async with _client(handle) as client:
        output = await make_get_employee_2fa_tool(client).fn(
            _EMPLOYEE, employee_id="emp_1"
        )

    assert '"phoneRegistered":true' in output
    assert "private@example.com" not in output
    assert "+58 412 123 4567" not in output


async def test_phone_registration_requires_portal_employee() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not run")

    async with _client(handle) as client:
        output = await make_register_2fa_phone_tool(client).fn(
            _MERCHANT, phone="+58 412 123 4567"
        )

    assert "employee identified by the portal" in output


async def test_cancel_order_uses_portal_employee() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"orderNumber": "197000001", "merchantId": 1}
            )
        return httpx.Response(200, json={"status": "cancelled"})

    async with _client(handle) as client:
        output = await make_cancel_order_tool(client).fn(
            _EMPLOYEE, order_number="197000001", reason_id=1
        )

    assert output == '{"status":"cancelled"}'
    assert len(requests) == 2
    assert b'"employeeId":"emp_1"' in requests[1].content


async def test_cancellation_reasons_use_portal_employee_role() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/employees/emp_1":
            return httpx.Response(200, json={"merchantId": 1, "role": "CASHIER"})
        assert request.url.path == "/api/v1/orders/cancellation-reasons"
        assert request.url.params["role"] == "CASHIER"
        return httpx.Response(200, json={"data": []})

    async with _client(handle) as client:
        output = await make_get_cancellation_reasons_tool(client).fn(_EMPLOYEE)

    assert output == '{"data":[]}'


async def test_store_list_is_scoped_to_principal_merchant() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/merchants/1/stores"
        return httpx.Response(200, json={"data": []})

    async with _client(handle) as client:
        output = await make_list_merchant_stores_tool(client).fn(_MERCHANT)

    assert output == '{"data":[]}'
