"""Contract tests for the agent-memory schema (Level 1 — no DB).

These lock the ADR-0002 shape against accidental drift: table names, the owned
`agent` schema, the generated `tsvector` columns + GIN indexes, and the
role/source guards. They introspect SQLAlchemy metadata only — no network, no
Postgres. Behavioural (real insert/query) tests land with the access layer.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Table

from agent.memory.base import Base
from agent.memory.models import ChatMessage, ChatSession, Episode, Fact

# Importing the models both registers their tables on Base.metadata and gives
# the tests a concrete handle on each mapped class.
_MODELS = (ChatSession, ChatMessage, Fact, Episode)


def _table(name: str) -> Table:
    return Base.metadata.tables[f"agent.{name}"]


def _assert_generated_gin(table_name: str, col_name: str, index_name: str) -> None:
    table = _table(table_name)
    col = table.c[col_name]
    assert isinstance(col, Column)
    assert col.computed is not None
    assert col.computed.persisted is True

    index = next(ix for ix in table.indexes if ix.name == index_name)
    assert index.dialect_options["postgresql"]["using"] == "gin"


def test_expected_tables_registered_under_agent_schema() -> None:
    assert {model.__tablename__ for model in _MODELS} == {
        "chat_sessions",
        "chat_messages",
        "facts",
        "episodes",
    }
    for model in _MODELS:
        assert _table(model.__tablename__).schema == "agent"


def test_facts_tsvector_is_generated_stored_with_gin_index() -> None:
    _assert_generated_gin("facts", "content_tsv", "ix_facts_content_tsv")


def test_episodes_tsvector_is_generated_stored_with_gin_index() -> None:
    _assert_generated_gin("episodes", "summary_tsv", "ix_episodes_summary_tsv")


def test_chat_sessions_user_id_is_nullable_and_indexed() -> None:
    """Which end-user a conversation belongs to (agent.identity.Principal) —
    nullable because most sessions have no identified user yet, indexed
    because it's the column future per-user queries filter by."""
    table = _table("chat_sessions")
    col = table.c["user_id"]
    assert col.nullable is True
    assert any("user_id" in ix.columns for ix in table.indexes)


def test_chat_message_guards_role_and_cascades_from_session() -> None:
    table = _table("chat_messages")
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("role" in str(c.sqltext) for c in checks)

    fk = next(iter(table.foreign_keys))
    assert fk.column.table.name == "chat_sessions"
    assert fk.ondelete == "CASCADE"


def test_chat_messages_order_by_a_generated_sequence() -> None:
    """Conversation order must not depend on the clock: `created_at` is the
    transaction timestamp, identical for messages written together."""
    seq = _table("chat_messages").c["seq"]
    assert isinstance(seq, Column)
    assert seq.identity is not None
    assert seq.nullable is False


def test_fact_guards_source() -> None:
    checks = [c for c in _table("facts").constraints if isinstance(c, CheckConstraint)]
    assert any("source" in str(c.sqltext) for c in checks)
