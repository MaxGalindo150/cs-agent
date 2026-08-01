"""Unit tests for the get_transactions BNPL tool (Level 1 — MockTransport, no
server). Same harness as test_bnpl_orders.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from agent.identity import Principal
from agent.tools.context import ToolContext
from agent.tools.implementations.bnpl.transactions import make_get_transactions_tool

_ALICE = ToolContext(principal=Principal(user_id="usr_alice"))
_TRANSACTIONS_PAGE: dict[str, Any] = {
    "data": [
        {
            "id": "txn_0001",
            "userId": "usr_alice",
            "type": "payment",
            "direction": "credit",
            "amount": 9700,
        }
    ],
    "total": 1,
}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://bnpl"
    )


def test_get_transactions_requires_identity() -> None:
    tool = make_get_transactions_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.requires_identity is True


async def test_get_transactions_filters_by_the_callers_own_user_id() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/transactions"
        assert request.url.params["userId"] == "usr_alice"
        assert "type" not in request.url.params
        return httpx.Response(200, json=_TRANSACTIONS_PAGE)

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE)

    assert json.loads(out) == _TRANSACTIONS_PAGE


async def test_get_transactions_passes_through_an_optional_type_filter() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["type"] == "payment"
        return httpx.Response(200, json=_TRANSACTIONS_PAGE)

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE, type="payment")

    assert json.loads(out) == _TRANSACTIONS_PAGE


def test_get_transactions_type_filter_is_constrained_to_known_values() -> None:
    """No open-ended string for the model to hallucinate into the query —
    the enum matches mock-server/src/schema/common.ts's TxnType."""
    tool = make_get_transactions_tool(httpx.AsyncClient(base_url="http://bnpl"))
    assert tool.input_schema["properties"]["type"]["enum"] == [
        "purchase",
        "payment",
        "refund",
        "fee",
        "interest",
        "points_earned",
        "points_redeemed",
        "adjustment",
    ]


async def test_get_transactions_refuses_a_leaked_transaction() -> None:
    """Never trust the upstream userId filter alone — if the service's own
    filter is wrong (or bypassed), refuse the whole response rather than
    leak another customer's transactions."""
    leaked = {**_TRANSACTIONS_PAGE, "data": [{**_TRANSACTIONS_PAGE["data"][0]}]}
    leaked["data"][0]["userId"] = "usr_bob"

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=leaked)

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_transactions_refuses_when_data_is_not_a_list() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": "not a list", "total": 1})

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_transactions_with_malformed_json_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE)

    assert "bad response from service" in out


async def test_get_transactions_non_200_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE)

    assert "Could not look up your transactions" in out
    assert "500" in out


async def test_get_transactions_service_down_is_honest() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _client(handle) as client:
        out = await make_get_transactions_tool(client).fn(_ALICE)

    assert "unavailable" in out
