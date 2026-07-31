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
    make_get_order_tool,
)

_ALICE = ToolContext(principal=Principal(user_id="usr_alice"))
_ORDER: dict[str, Any] = {
    "id": "ord_0001",
    "status": "active",
    "totalAmount": 29000,
    "userId": "usr_alice",
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
        assert request.url.path == "/api/v1/orders"
        assert request.url.params["userId"] == "usr_alice"
        return httpx.Response(200, json={"data": [_ORDER], "total": 1})

    async with _client(handle) as client:
        out = await make_get_my_orders_tool(client).fn(_ALICE)

    assert json.loads(out) == {"data": [_ORDER], "total": 1}


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
