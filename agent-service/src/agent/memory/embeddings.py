"""Embeddings for semantic memory — a thin, provider-neutral seam (ADR-0003).

Facts are retrieved by *meaning*, which needs vectors. Anthropic has no
first-party embeddings API — it recommends Voyage AI — so this call always goes
to a third party. We deliberately do NOT pull the ``voyageai`` SDK: it drags
``aiohttp`` (a second HTTP stack) plus ``langchain-core`` / ``langsmith`` /
``tokenizers`` / ``numpy`` transitively — the heavy-framework bloat CLAUDE.md
§2.5/§5 rules out, and dead weight in a Cloud Run image for what is one POST.
Instead this calls Voyage's ``/v1/embeddings`` endpoint over the ``httpx``
client we already depend on.

The ``Embedder`` protocol is the swap point (ADR-0003 §8): a different provider
(OpenAI, a local model) is a new implementation behind the same two methods —
never a change to the store or the facade. Voyage's ``input_type`` distinction
(``query`` vs ``document``) is part of the contract because it measurably
improves retrieval.
"""

from __future__ import annotations

from typing import Protocol

import httpx

_VOYAGE_BASE_URL = "https://api.voyageai.com/v1"


class EmbeddingError(RuntimeError):
    """An embedding call failed or returned something unusable.

    One exception type so callers (e.g. the fact store's FTS fallback, ADR-0003
    §7) have a single thing to catch, whether the failure was transport, HTTP
    status, or a malformed body.
    """


class Embedder(Protocol):
    """Turns text into vectors. Two call sites, two methods (ADR-0003 §5/§6)."""

    @property
    def model(self) -> str:
        """The model id, recorded on each embedded row so a model change can be
        detected and a re-embed sweep can target only stale rows (ADR-0003 §4)."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (retrieval side)."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed one or more stored facts (write side); order is preserved."""
        ...


class VoyageEmbedder:
    """:class:`Embedder` over Voyage's REST API, via an owned ``httpx`` client.

    Owns an ``AsyncClient`` for connection reuse; the transport wires it at
    startup and calls :meth:`aclose` at shutdown (same lifecycle discipline as
    :class:`~agent.memory.db.Database`). Tests inject a ``transport``
    (``httpx.MockTransport``) so no network is touched.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "voyage-3.5",
        dims: int = 1024,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._dims = dims
        self._client = httpx.AsyncClient(
            base_url=_VOYAGE_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], input_type="query")
        return vectors[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed(texts, input_type="document")

    async def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        try:
            response = await self._client.post(
                "/embeddings",
                json={
                    "model": self._model,
                    "input": texts,
                    "input_type": input_type,
                    "output_dimension": self._dims,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Voyage request failed: {exc}") from exc

        try:
            # The API does not guarantee response order — realign by `index`.
            rows = sorted(payload["data"], key=lambda row: row["index"])
            return [[float(x) for x in row["embedding"]] for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(f"Voyage response malformed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
