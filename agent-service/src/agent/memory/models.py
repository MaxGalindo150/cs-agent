"""SQLAlchemy models for agent memory & sessions (ADR-0002).

Four tables under the owned ``agent`` schema:

- ``chat_sessions`` / ``chat_messages`` — conversation persistence. The raw
  message log is what consolidation reads from.
- ``facts``    — semantic memory (durable facts), full-text searchable.
- ``episodes`` — episodic memory (dated, distilled), full-text searchable.

Full-text search uses a generated ``tsvector`` column (``spanish`` dictionary)
with a GIN index — the database maintains it automatically, so there are no
triggers to write or keep in sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.memory.base import Base

# Stored embedding dimension for facts (ADR-0003). A vector column's dimension
# is part of its type, so it is fixed at the DDL level and cannot vary per
# request — it must equal the service's EMBEDDING_DIMS (default 1024). Moving to
# an embedding model with a different dimension requires a migration + re-embed.
_FACT_EMBEDDING_DIMS = 1024


class ChatSession(Base):
    """One conversation. Sessions are a first-class entity so the product can
    offer "new chat" / switch between past conversations."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(Text)
    # Which end-user this conversation belongs to (agent.identity.Principal,
    # resolved by service/core/identity.py). Nullable — most sessions today
    # have no identified user (no real auth yet), and a session must be
    # creatable before identity is known. Not a tenant/org column — one
    # end-user, no isolation semantics (CLAUDE.md §9).
    #
    # NOT a verified identity today — self-asserted via a dev-only header
    # stub. Do not use this column for authorization until that stub is
    # replaced by real auth. See docs/SECURITY.md §1-2.
    user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessage(Base):
    """Raw conversation log. Consolidation reads unconsolidated rows from here
    to distil durable ``facts`` / ``episodes``."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role_valid"),
        Index("ix_chat_messages_session_seq", "session_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Insertion order, guaranteed. `created_at` cannot order a conversation:
    # now() is the *transaction* timestamp, so messages written in one
    # transaction share it and the tiebreak would fall to a random UUID. A
    # sequence gives a total, monotonic order independent of the clock.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Which channel the message came in through (Waku's chat_log.source:
    # cli/voice/telegram — here whatsapp/webchat/api). Open-ended, so no CHECK,
    # unlike facts.source. Nullable until the transport threads it through.
    source: Mapped[str | None] = mapped_column(String(32))
    # Per-turn telemetry (gate decision, latency, tools, iterations) — ADR-0002.
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    consolidated: Mapped[bool] = mapped_column(
        server_default="false", default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Fact(Base):
    """Semantic memory: a durable fact about the user, their people, or their
    projects. Retrieved by full-text search over ``content_tsv``."""

    __tablename__ = "facts"
    __table_args__ = (
        CheckConstraint("source IN ('user', 'consolidation')", name="source_valid"),
        Index("ix_facts_content_tsv", "content_tsv", postgresql_using="gin"),
        # Vector ANN index (ADR-0003), mirroring docs/rag-design.md: HNSW over
        # the halfvec column with cosine distance. `content_tsv` + its GIN index
        # are retained for the FTS fallback and a future hybrid step.
        Index(
            "ix_facts_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), server_default="user", nullable=False
    )
    # Which end-user this fact is about (agent.identity.Principal). Nullable
    # for now: nothing writes facts yet (no remember tool, no consolidation —
    # agent/memory/__init__.py), so there is no existing row to migrate. Every
    # fact is inherently personal (see the class docstring) — there is no
    # "global fact" use case — so the write path being built next must always
    # supply this. NOT a verified identity today: see docs/SECURITY.md §1-2.
    user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Generated + STORED: the DB recomputes it whenever subject/content change.
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('spanish', subject || ' ' || content)", persisted=True),
    )
    # Semantic-memory vector (ADR-0003). NULL until embedded, so a fact can exist
    # FTS-only. fp16 `halfvec` per docs/rag-design.md.
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(_FACT_EMBEDDING_DIMS))
    # Which model produced `embedding` — lets a model change be detected and a
    # re-embed sweep target only stale rows.
    embedding_model: Mapped[str | None] = mapped_column(Text)


class Episode(Base):
    """Episodic memory: a dated, distilled summary of something that happened.
    Retrieved by full-text search over ``summary_tsv``."""

    __tablename__ = "episodes"
    __table_args__ = (
        Index("ix_episodes_summary_tsv", "summary_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    happened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Which end-user this episode is about — same rationale as Fact.user_id
    # above: nullable for now (nothing writes episodes yet), but every episode
    # is inherently personal, so the future write path must always supply it.
    # NOT a verified identity today: see docs/SECURITY.md §1-2.
    user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    summary_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('spanish', summary)", persisted=True),
    )
