"""Unit tests for the get_order BNPL tool (Level 1 — MockTransport, no server).

The tool is bound to an injected httpx client, so we drive it with a mock
transport: no running mock-server, no network. Each case asserts the tool's
honest output — the string the model would observe.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from agent.identity import Principal
from agent.tools.context import ToolContext
from agent.tools.implementations.bnpl.orders import (
    make_get_my_orders_tool,
    make_get_order_installments_tool,
    make_get_order_shipment_tool,
    make_get_order_tool,
)

_ALICE = ToolContext(principal=Principal(user_id="usr_alice"))
_ORDER: dict[str, Any] = {
    "id": "ord_0001",
    "status": "active",
    "totalAmount": 29000,
    "userId": "usr_alice",
}
_SHIPMENT: dict[str, Any] = {
    "id": "shp_0001",
    "orderId": "ord_0001",
    "userId": "usr_alice",
    "carrier": "fedex",
    "status": "in_transit",
    "events": [],
}
_INSTALLMENT: dict[str, Any] = {
    "id": "ins_0001",
    "orderId": "ord_0001",
    "userId": "usr_alice",
    "number": 1,
    "amountDue": 9700,
    "status": "paid",
}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://bnpl"
    )


def test_get_order_requires_identity() -> None:
    tool = make_get_order_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.requires_identity is True


async def test_get_order_returns_the_order_json() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orders/ord_0001"
        return httpx.Response(200, json=_ORDER)

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(_ALICE, order_id="ord_0001")

    assert json.loads(out) == _ORDER


async def test_get_order_missing_id_is_a_helpful_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:  # never called
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(_ALICE)  # no order_id

    assert "needs an order_id" in out


async def test_get_order_404_is_an_honest_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(_ALICE, order_id="ord_9999")

    assert out == "No order found with id 'ord_9999'."


async def test_get_order_non_200_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(_ALICE, order_id="ord_0001")

    assert "Could not look up order 'ord_0001'" in out
    assert "500" in out


async def test_get_order_service_down_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(_ALICE, order_id="ord_0001")

    assert "unavailable" in out


async def test_get_order_belonging_to_another_user_is_refused() -> None:
    """The whole point: an order_id alone is not proof of ownership — Bob
    cannot see Alice's order even if he supplies (or hallucinates) her id."""
    bob = ToolContext(principal=Principal(user_id="usr_bob"))

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ORDER)  # owned by usr_alice

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(bob, order_id="ord_0001")

    # Same shape as a genuine 404 — never confirms the order exists for
    # someone else.
    assert out == "No order found with id 'ord_0001'."


async def test_get_order_with_malformed_json_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(_ALICE, order_id="ord_0001")

    assert "bad response from service" in out


# ---- get_order_shipment ----------------------------------------------------


def test_get_order_shipment_requires_identity() -> None:
    tool = make_get_order_shipment_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.requires_identity is True


async def test_get_order_shipment_returns_the_shipment_json() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orders/ord_0001/shipment"
        return httpx.Response(200, json=_SHIPMENT)

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(_ALICE, order_id="ord_0001")

    assert json.loads(out) == _SHIPMENT


async def test_get_order_shipment_missing_id_is_a_helpful_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:  # never called
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(_ALICE)  # no order_id

    assert "needs an order_id" in out


async def test_get_order_shipment_404_is_an_honest_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(_ALICE, order_id="ord_9999")

    assert out == "No shipment found for order 'ord_9999'."


async def test_get_order_shipment_non_200_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(_ALICE, order_id="ord_0001")

    assert "Could not look up the shipment for order 'ord_0001'" in out
    assert "500" in out


async def test_get_order_shipment_service_down_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(_ALICE, order_id="ord_0001")

    assert "unavailable" in out


async def test_get_order_shipment_belonging_to_another_user_is_refused() -> None:
    """Same invariant as get_order: an order_id alone is not proof of
    ownership. The shipment's own userId is what's checked."""
    bob = ToolContext(principal=Principal(user_id="usr_bob"))

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SHIPMENT)  # owned by usr_alice

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(bob, order_id="ord_0001")

    assert out == "No shipment found for order 'ord_0001'."


async def test_get_order_shipment_with_malformed_json_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    async with _client(handle) as client:
        out = await make_get_order_shipment_tool(client).fn(_ALICE, order_id="ord_0001")

    assert "bad response from service" in out


# ---- get_order_installments -------------------------------------------------


def test_get_order_installments_requires_identity() -> None:
    tool = make_get_order_installments_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.requires_identity is True


async def test_get_order_installments_returns_the_installments_json() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orders/ord_0001/installments"
        return httpx.Response(200, json={"data": [_INSTALLMENT]})

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert json.loads(out) == {"data": [_INSTALLMENT]}


async def test_get_order_installments_missing_id_is_a_helpful_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:  # never called
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(_ALICE)  # no order_id

    assert "needs an order_id" in out


async def test_get_order_installments_404_is_an_honest_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_9999"
        )

    assert out == "No order found with id 'ord_9999'."


async def test_get_order_installments_non_200_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert "Could not look up installments for order 'ord_0001'" in out
    assert "500" in out


async def test_get_order_installments_service_down_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert "unavailable" in out


async def test_get_order_installments_belonging_to_another_user_is_refused() -> None:
    """Same invariant as get_order: an order_id alone is not proof of
    ownership. Each installment's own userId is what's checked."""
    bob = ToolContext(principal=Principal(user_id="usr_bob"))

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [_INSTALLMENT]})  # owned by usr_alice

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            bob, order_id="ord_0001"
        )

    assert out == "No order found with id 'ord_0001'."


async def test_get_order_installments_with_no_installments_is_refused() -> None:
    """An empty list can't be proven to belong to the caller — refused the
    same as a 404, not returned unchecked."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert out == "No order found with id 'ord_0001'."


async def test_get_order_installments_with_malformed_json_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert "bad response from service" in out


async def test_get_order_installments_refuses_a_non_dict_top_level_body() -> None:
    """resp.json() can decode to any JSON type — a bare list or null must
    not reach body.get() and raise AttributeError."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert out == "No order found with id 'ord_0001'."


async def test_get_order_installments_refuses_a_null_top_level_body() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"null")

    async with _client(handle) as client:
        out = await make_get_order_installments_tool(client).fn(
            _ALICE, order_id="ord_0001"
        )

    assert out == "No order found with id 'ord_0001'."


# ---- get_my_orders ---------------------------------------------------------


def test_get_my_orders_requires_identity() -> None:
    tool = make_get_my_orders_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.requires_identity is True


def test_get_my_orders_exposes_no_properties_for_the_model_to_fill() -> None:
    """No user_id/userId property to hallucinate into — the caller's identity
    comes only from ctx.principal, never from model-supplied arguments."""
    tool = make_get_my_orders_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.input_schema == {"type": "object", "properties": {}}


async def test_get_my_orders_filters_by_the_callers_own_user_id() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orders":
            assert request.url.params["userId"] == "usr_alice"
            return httpx.Response(200, json={"data": [_ORDER], "total": 1})
        assert request.url.path == "/api/v1/orders/ord_0001/shipment"
        return httpx.Response(200, json=_SHIPMENT)

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    body = json.loads(out)
    assert body["total"] == 1
    assert body["data"][0]["id"] == "ord_0001"
    assert body["data"][0]["shipmentStatus"] == "in_transit"


async def test_get_my_orders_omits_shipment_fields_for_a_mismatched_owner() -> None:
    """The order list is already filtered by userId server-side, but the
    shipment's own userId is still checked — never trust the upstream filter
    alone (same invariant as get_order_shipment)."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orders":
            return httpx.Response(200, json={"data": [_ORDER], "total": 1})
        mismatched = {**_SHIPMENT, "userId": "usr_bob"}
        return httpx.Response(200, json=mismatched)

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    body = json.loads(out)
    assert "shipmentStatus" not in body["data"][0]


async def test_get_my_orders_omits_shipment_fields_when_the_lookup_fails() -> None:
    """Best-effort enrichment: one order's shipment lookup failing must not
    fail the whole list, only leave that order without shipment fields."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orders":
            return httpx.Response(200, json={"data": [_ORDER], "total": 1})
        return httpx.Response(404, json={"error": "not found"})

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    body = json.loads(out)
    assert "shipmentStatus" not in body["data"][0]


async def test_get_my_orders_omits_shipment_fields_when_the_service_is_down() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orders":
            return httpx.Response(200, json={"data": [_ORDER], "total": 1})
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    body = json.loads(out)
    assert "shipmentStatus" not in body["data"][0]


async def test_get_my_orders_omits_shipment_fields_on_malformed_shipment_json() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orders":
            return httpx.Response(200, json={"data": [_ORDER], "total": 1})
        return httpx.Response(200, content=b"not json")

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    body = json.loads(out)
    assert "shipmentStatus" not in body["data"][0]


async def test_get_my_orders_with_no_orders_returns_an_empty_list() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orders"
        return httpx.Response(200, json={"data": [], "total": 0})

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert json.loads(out) == {"data": [], "total": 0}


async def test_get_my_orders_with_malformed_json_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_my_orders_refuses_a_non_dict_top_level_body() -> None:
    """resp.json() can decode to any JSON type — a bare list or null must
    not reach body.get() and raise AttributeError."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_my_orders_refuses_a_null_top_level_body() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"null")

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_my_orders_refuses_when_data_is_not_a_list_of_dicts() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": ["not a dict"], "total": 1})

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_my_orders_non_200_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert "Could not look up your orders" in out
    assert "500" in out


async def test_get_my_orders_service_down_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert "unavailable" in out
