"""LLM client wiring for the agent service.

The provider client is a process-level resource: built once at startup, reused
across requests, closed on shutdown. Routes reach it through a FastAPI
dependency, so tests can override it with a fake — no network, no API key.

Anthropic-only for now. When a second provider lands, this module is the seam
that grows into a provider abstraction (it stays localized to `service/`); the
agent loop already runs against whatever client is injected here.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from fastapi import Request

from service.core.config import Settings


def build_anthropic_client(settings: Settings) -> AsyncAnthropic:
    """Construct the Anthropic client from config (the key is never hardcoded)."""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def get_llm_client(request: Request) -> AsyncAnthropic:
    """Dependency: hand routes the process-wide client stored at startup."""
    client: AsyncAnthropic = request.app.state.llm
    return client
