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
from agent.decide.jev import JevClient, JevConfig
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


def build_decider(settings: Settings) -> JevClient | None:
    """Process-wide client for the harness's decision model (ADR-0004), or
    ``None`` when no key is configured — which disables every decision site
    and leaves the harness exactly as it was. Owns an httpx client; closed at
    shutdown like the embedder."""
    if not settings.typesafe_api_key:
        return None
    return JevClient(
        JevConfig(
            api_key=settings.typesafe_api_key,
            model=settings.jev_model,
            base_url=settings.jev_base_url,
            timeout_s=settings.jev_timeout_s,
        )
    )


def build_service_agent(
    settings: Settings,
    *,
    client: AsyncAnthropic,
    db: Database,
    tools: ToolRegistry,
    embedder: Embedder | None,
    decider: JevClient | None = None,
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
        decider=decider,
        decision_threshold=settings.jev_confidence_threshold,
        max_tool_calls=settings.max_tool_calls_per_turn,
        max_turn_tokens=settings.max_tokens_per_turn,
    )


def get_agent(request: Request) -> Agent:
    """Dependency: the process-wide Agent assembled at startup."""
    agent: Agent = request.app.state.agent
    return agent


def get_agent_optional(request: Request) -> Agent | None:
    """Dependency for routes that *can* use the Agent but must keep working
    without one (the feedback route, the worker): ``None`` when the app was
    built without a lifespan, as the transport-only tests do."""
    agent: Agent | None = getattr(request.app.state, "agent", None)
    return agent


def get_database(request: Request) -> Database:
    """Dependency: the process-wide connection pool.

    For transport-only reads that never go through the agent (browsing past
    conversations — see api/v1/sessions.py). Handlers take a short session from
    it and hand it back; they never hold one across a slow call.
    """
    db: Database = request.app.state.db
    return db
