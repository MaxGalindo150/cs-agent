"""Order cards and follow-up suggestions drawn in the aliado's chat."""

from __future__ import annotations

import json

from agent.tools.context import ToolContext
from agent.tools.implementations.merchant.orders import order_cards
from agent.tools.implementations.merchant.suggestions import make_suggest_replies_tool


def test_search_results_become_cards_with_the_short_status() -> None:
    output = json.dumps(
        {
            "orders": [
                {
                    "order_uuid": "u1",
                    "order_number": 924141,
                    "created_at": "2026-10-14 19:24 (hora de Venezuela)",
                    "amount": 25,
                    "status": "Abierta: esperando al comprador",
                    "store": "PX Cotidiana",
                    "channel": "QR",
                    "delivery_status": "No aplica",
                }
            ],
            "more_available": False,
        }
    )

    assert order_cards(output) == {
        "type": "orders",
        "orders": [
            {
                "order_uuid": "u1",
                "order_number": 924141,
                "created_at": "2026-10-14 19:24 (hora de Venezuela)",
                "amount": 25,
                "status": "Abierta",
                "store": "PX Cotidiana",
                "channel": "QR",
            }
        ],
    }


def test_an_order_detail_becomes_one_card() -> None:
    detail = {"order_uuid": "u1", "order_number": 7, "status": "Pagada", "buyer": {}}

    cards = order_cards(json.dumps(detail))

    assert cards is not None
    assert [c["order_number"] for c in cards["orders"]] == [7]


def test_text_results_draw_nothing() -> None:
    assert order_cards("No orders match those filters.") is None
    assert order_cards(json.dumps({"orders": []})) is None


async def test_suggestions_are_trimmed_and_capped() -> None:
    tool = make_suggest_replies_tool()
    options = ["  Ver detalle  ", "", "x" * 60, "Cuarta", "Quinta"]

    output = await tool.fn(ctx=ToolContext(), options=options)

    assert tool.display is not None
    assert tool.display(output) == {
        "type": "suggestions",
        "options": ["Ver detalle", "x" * 40, "Cuarta"],
    }
    assert tool.silent and tool.ends_turn
