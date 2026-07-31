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

from agent.tools.implementations.bnpl.orders import make_get_order_tool

_ORDER: dict[str, Any] = {"id": "ord_0001", "status": "active", "totalAmount": 29000}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://bnpl"
    )


async def test_get_order_returns_the_order_json() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orders/ord_0001"
        return httpx.Response(200, json=_ORDER)

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(order_id="ord_0001")

    assert json.loads(out) == _ORDER


async def test_get_order_missing_id_is_a_helpful_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:  # never called
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn()  # no order_id

    assert "needs an order_id" in out


async def test_get_order_404_is_an_honest_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(order_id="ord_9999")

    assert out == "No order found with id 'ord_9999'."


async def test_get_order_non_200_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(order_id="ord_0001")

    assert "Could not look up order 'ord_0001'" in out
    assert "500" in out


async def test_get_order_service_down_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_order_tool(client).fn(order_id="ord_0001")

    assert "unavailable" in out
