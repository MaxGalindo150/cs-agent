"""Unit tests for the Voyage embedder (Level 1 — deterministic, no network).

An ``httpx.MockTransport`` stands in for Voyage: every request is captured so we
can assert on the wire shape (model, ``input_type``, ``output_dimension``, auth
header), and canned responses drive the parsing paths — including out-of-order
data (must realign by ``index``) and the two failure modes that must surface as
``EmbeddingError`` so the store's FTS fallback (ADR-0003 §7) has one thing to
catch.
"""

from __future__ import annotations

import json

import httpx
import pytest

from agent.memory.embeddings import EmbeddingError, VoyageEmbedder


def _embedder(
    handler: httpx.MockTransport,
    *,
    model: str = "voyage-3.5",
    dims: int = 1024,
) -> VoyageEmbedder:
    return VoyageEmbedder("vk-test", model=model, dims=dims, transport=handler)


async def test_embed_query_sends_query_input_type_and_returns_vector() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
        )

    vector = await _embedder(httpx.MockTransport(handler)).embed_query("vpn error")

    assert vector == [0.1, 0.2, 0.3]
    body = json.loads(seen[0].content)
    assert body["input"] == ["vpn error"]
    assert body["input_type"] == "query"
    assert body["model"] == "voyage-3.5"
    assert body["output_dimension"] == 1024
    assert seen[0].headers["authorization"] == "Bearer vk-test"


async def test_embed_documents_uses_document_input_type_and_preserves_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Return rows out of order — the embedder must realign by `index`.
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.9]},
                    {"index": 0, "embedding": [0.1]},
                ]
            },
        )

    vectors = await _embedder(httpx.MockTransport(handler)).embed_documents(
        ["primero", "segundo"]
    )

    assert vectors == [[0.1], [0.9]]


async def test_embed_documents_empty_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be made for an empty batch")

    assert await _embedder(httpx.MockTransport(handler)).embed_documents([]) == []


async def test_http_error_is_wrapped_as_embedding_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(EmbeddingError):
        await _embedder(httpx.MockTransport(handler)).embed_query("x")


async def test_malformed_response_is_wrapped_as_embedding_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(EmbeddingError):
        await _embedder(httpx.MockTransport(handler)).embed_query("x")
