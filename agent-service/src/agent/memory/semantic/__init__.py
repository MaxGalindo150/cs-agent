"""Semantic memory — durable facts, retrieved by full text (pgvector: ADR-0003)."""

from __future__ import annotations

from agent.memory.semantic.store import PostgresFactStore

__all__ = ["PostgresFactStore"]
