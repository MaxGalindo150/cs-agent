"""Merchant (aliado) support tools.

These tools wrap the merchant-mock-server HTTP API (port 3002). They follow
the same conventions as the BNPL tools under ``implementations/bnpl/``:

- ``make_*_tool(client: httpx.AsyncClient) -> Tool`` factory pattern
- All HTTP errors → honest text strings, never raised exceptions
- ``requires_identity=True`` — the merchant principal must be resolved
- Amounts in cents (the tool passes raw JSON through, the description tells
  the model to divide by 100)
- Order numbers are 9-digit numbers, not prefixed ids
"""
