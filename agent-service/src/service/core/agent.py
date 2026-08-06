"""Agent wiring: assemble the process-wide Agent at startup, hand it to routes.

Same shape as ``service/core/llm.py`` — build the durable resources once in the
app lifespan, store the Agent on ``app.state``, and reach it through a FastAPI
dependency (overridable in tests). This module is the one seam where the service
``Settings`` crosses into the brain: it reads config here and passes only plain
values into ``build_agent`` (CLAUDE.md §4), so nothing under ``agent/`` ever sees
``Settings``.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from fastapi import Request

from agent.app import Agent, build_agent
from agent.memory.db import Database, DatabaseConfig
from agent.memory.embeddings import Embedder, VoyageEmbedder
from agent.tools.registry import ToolRegistry
from service.core.config import Settings


def build_database(settings: Settings) -> Database:
    """Process-wide async Postgres pool for the agent's memory & sessions."""
    return Database(DatabaseConfig(url=settings.agent_database_url))


def build_embedder(settings: Settings) -> VoyageEmbedder:
    """Process-wide embedder for semantic memory (Voyage, over an owned httpx
    client). Closed at shutdown, same as the DB pool and LLM client."""
    return VoyageEmbedder(
        settings.voyage_api_key,
        model=settings.embedding_model,
        dims=settings.embedding_dims,
    )


def build_service_agent(
    settings: Settings,
    *,
    client: AsyncAnthropic,
    db: Database,
    tools: ToolRegistry,
    embedder: Embedder | None,
    soul: str = "",
) -> Agent:
    """Assemble the Agent from process-wide parts via the brain-side factory."""
    return build_agent(
        client=client,
        db=db,
        tools=tools,
        chat_model=settings.anthropic_chat_model,
        fast_model=settings.anthropic_fast_model,
        trace_dir=settings.trace_dir,
        otel_endpoint=settings.otel_endpoint or None,
        embedder=embedder,
        soul=soul,
    )


def get_agent(request: Request) -> Agent:
    """Dependency: the process-wide Agent assembled at startup.

    Selects between the buyer and merchant agents based on the
    ``X-Agent-Profile`` header (default: buyer).
    """
    profile = request.headers.get("X-Agent-Profile", "buyer")
    if profile == "merchant":
        agent: Agent = request.app.state.merchant_agent
    else:
        agent = request.app.state.agent
    return agent


def get_database(request: Request) -> Database:
    """Dependency: the process-wide connection pool.

    For transport-only reads that never go through the agent (browsing past
    conversations — see api/v1/sessions.py). Handlers take a short session from
    it and hand it back; they never hold one across a slow call.
    """
    db: Database = request.app.state.db
    return db
