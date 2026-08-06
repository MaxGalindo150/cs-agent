"""Merchant catalog tools scoped to the identified portal merchant."""

from __future__ import annotations

import httpx

from agent.tools.context import ToolContext
from agent.tools.registry import Tool


def make_list_merchant_stores_tool(client: httpx.AsyncClient) -> Tool:
    async def list_merchant_stores(ctx: ToolContext) -> str:
        assert ctx.principal is not None
        merchant_id = ctx.principal.merchant_id or ""
        if not merchant_id:
            return "No merchant is identified for this conversation."
        try:
            response = await client.get(f"/api/v1/merchants/{merchant_id}/stores")
        except httpx.RequestError:
            return "The merchant service is unavailable right now — try again shortly."
        if response.status_code != 200:
            return f"Could not list merchant stores (status {response.status_code})."
        return response.text

    return Tool(
        name="list_merchant_stores",
        progress_label="Listing merchant stores",
        description=(
            "List stores owned by the authenticated merchant, including their UUIDs "
            "and names. Use this before store-scoped operations such as daily "
            "conciliation when no store is already identified."
        ),
        input_schema={"type": "object", "properties": {}},
        fn=list_merchant_stores,
        requires_identity=True,
    )
