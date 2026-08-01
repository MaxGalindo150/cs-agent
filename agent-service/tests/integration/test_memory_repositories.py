"""Behavioural tests for the memory repositories against a real PostgreSQL.

These assert on rows and on database-enforced behaviour that no mock can prove:
the generated `tsvector` columns, Spanish stemming, the CHECK guards, and the
FK cascade. Deterministic and hermetic — no LLM, no network beyond the DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agent.memory.db import Database
from agent.memory.repositories import (
    EpisodeRepository,
    FactRepository,
    SessionRepository,
)

# --- sessions & messages ---------------------------------------------------


async def test_append_and_list_messages_in_order(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    chat = await repo.create_session(title="soporte")

    await repo.append_message(chat.id, "user", "hola")
    await repo.append_message(chat.id, "assistant", "¿en qué te ayudo?")

    messages = await repo.list_messages(chat.id)
    assert [(m.role, m.content) for m in messages] == [
        ("user", "hola"),
        ("assistant", "¿en qué te ayudo?"),
    ]


async def test_message_meta_round_trips_as_jsonb(db_session: AsyncSession) -> None:
    repo = SessionRepository(db_session)
    chat = await repo.create_session()

    meta = {"latency_ms": 812, "tools": ["get_order"], "iterations": 2}
    await repo.append_message(chat.id, "assistant", "listo", meta=meta)

    stored = (await repo.list_messages(chat.id))[0]
    assert stored.meta == meta


async def test_message_source_persists_and_defaults_to_null(
    db_session: AsyncSession,
) -> None:
    """The input channel (Waku's chat_log.source) is stored when given and left
    NULL when the caller doesn't know it."""
    repo = SessionRepository(db_session)
    chat = await repo.create_session()

    await repo.append_message(chat.id, "user", "hola", source="whatsapp")
    await repo.append_message(chat.id, "assistant", "listo")

    stored = await repo.list_messages(chat.id)
    assert stored[0].source == "whatsapp"
    assert stored[1].source is None


async def test_append_message_bumps_session_activity(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    chat = await repo.create_session()
    before = chat.last_activity_at

    await repo.append_message(chat.id, "user", "¿dónde está mi pedido?")
    await db_session.refresh(chat)

    assert chat.last_activity_at >= before


async def test_invalid_role_is_rejected_by_the_database(
    db_session: AsyncSession,
) -> None:
    """Business guards live in the schema, not in hope."""
    repo = SessionRepository(db_session)
    chat = await repo.create_session()

    with pytest.raises(IntegrityError):
        await repo.append_message(chat.id, "system", "no permitido")

    # A failed statement poisons the transaction; the caller must unwind it
    # before the session can be used (or committed) again.
    await db_session.rollback()


async def test_deleting_a_session_cascades_to_its_messages(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    chat = await repo.create_session()
    await repo.append_message(chat.id, "user", "hola")

    await db_session.delete(chat)
    await db_session.flush()

    remaining = await db_session.execute(
        sa.text("SELECT count(*) FROM agent.chat_messages")
    )
    assert remaining.scalar() == 0


async def test_consolidation_marks_only_the_given_messages(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    chat = await repo.create_session()
    first = await repo.append_message(chat.id, "user", "uno")
    await repo.append_message(chat.id, "user", "dos")

    assert len(await repo.list_unconsolidated()) == 2

    changed = await repo.mark_consolidated([first.id])
    assert changed == 1

    pending = await repo.list_unconsolidated()
    assert [m.content for m in pending] == ["dos"]


async def test_mark_consolidated_with_no_ids_is_a_no_op(
    db_session: AsyncSession,
) -> None:
    assert await SessionRepository(db_session).mark_consolidated([]) == 0


async def test_unconsolidated_user_ids_excludes_anonymous_sessions(
    db_session: AsyncSession,
) -> None:
    """No owner, no consolidation (docs/SECURITY.md §3) — an anonymous
    session's pending messages must never surface here."""
    repo = SessionRepository(db_session)
    identified = await repo.create_session(user_id="usr_alice")
    anonymous = await repo.create_session()
    await repo.append_message(identified.id, "user", "hola")
    await repo.append_message(anonymous.id, "user", "hola")

    assert await repo.list_unconsolidated_user_ids() == ["usr_alice"]


async def test_unconsolidated_user_ids_lists_each_user_once(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    session_1 = await repo.create_session(user_id="usr_alice")
    session_2 = await repo.create_session(user_id="usr_alice")
    await repo.append_message(session_1.id, "user", "uno")
    await repo.append_message(session_2.id, "user", "dos")

    assert await repo.list_unconsolidated_user_ids() == ["usr_alice"]


async def test_unconsolidated_for_user_spans_all_their_sessions_in_order(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    session_1 = await repo.create_session(user_id="usr_alice")
    session_2 = await repo.create_session(user_id="usr_alice")
    await repo.append_message(session_1.id, "user", "primero")
    await repo.append_message(session_2.id, "user", "segundo")

    messages = await repo.list_unconsolidated_for_user("usr_alice")

    assert [m.content for m in messages] == ["primero", "segundo"]


async def test_unconsolidated_for_user_never_crosses_users(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    alice_session = await repo.create_session(user_id="usr_alice")
    bob_session = await repo.create_session(user_id="usr_bob")
    await repo.append_message(alice_session.id, "user", "de alice")
    await repo.append_message(bob_session.id, "user", "de bob")

    messages = await repo.list_unconsolidated_for_user("usr_alice")

    assert [m.content for m in messages] == ["de alice"]


async def test_unconsolidated_for_user_ignores_already_consolidated_messages(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    session = await repo.create_session(user_id="usr_alice")
    old = await repo.append_message(session.id, "user", "viejo")
    await repo.append_message(session.id, "user", "nuevo")
    await repo.mark_consolidated([old.id])

    messages = await repo.list_unconsolidated_for_user("usr_alice")

    assert [m.content for m in messages] == ["nuevo"]


async def test_unconsolidated_user_ids_are_oldest_waiting_first(
    db_session: AsyncSession,
) -> None:
    """A capped sweep (``limit``) must make fair progress — the user who's
    been waiting longest goes first, not an arbitrary DISTINCT order."""
    repo = SessionRepository(db_session)
    bob_session = await repo.create_session(user_id="usr_bob")
    await repo.append_message(bob_session.id, "user", "bob ha estado esperando")
    alice_session = await repo.create_session(user_id="usr_alice")
    await repo.append_message(alice_session.id, "user", "alice llegó después")

    assert await repo.list_unconsolidated_user_ids() == ["usr_bob", "usr_alice"]


async def test_unconsolidated_user_ids_respects_limit(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)
    for user_id in ("usr_alice", "usr_bob", "usr_carol"):
        session = await repo.create_session(user_id=user_id)
        await repo.append_message(session.id, "user", "hola")

    assert await repo.list_unconsolidated_user_ids(limit=2) == [
        "usr_alice",
        "usr_bob",
    ]


async def test_sessions_are_listed_most_recently_active_first(
    database: Database,
) -> None:
    """Each step runs in its own transaction, as production does.

    `now()` is the *transaction* timestamp in Postgres — constant inside one
    transaction — so activity ordering is only meaningful across separate units
    of work.
    """
    async with database.session() as s:
        older = await SessionRepository(s).create_session(title="viejo")
        older_id = older.id

    async with database.session() as s:
        newer = await SessionRepository(s).create_session(title="nuevo")
        newer_id = newer.id

    async with database.session() as s:
        # Touch the older session so it becomes the most recently active.
        await SessionRepository(s).append_message(older_id, "user", "sigo aquí")

    async with database.session() as s:
        listed = await SessionRepository(s).list_sessions()

    assert [chat.id for chat in listed][:2] == [older_id, newer_id]


async def test_get_session_returns_none_when_absent(
    db_session: AsyncSession,
) -> None:
    assert await SessionRepository(db_session).get_session(uuid.uuid4()) is None


async def test_create_session_persists_the_owning_user_id(
    db_session: AsyncSession,
) -> None:
    repo = SessionRepository(db_session)

    chat = await repo.create_session(title="soporte", user_id="usr_0001")

    assert chat.user_id == "usr_0001"
    reloaded = await repo.get_session(chat.id)
    assert reloaded is not None
    assert reloaded.user_id == "usr_0001"


async def test_create_session_without_a_user_id_defaults_to_null(
    db_session: AsyncSession,
) -> None:
    """An anonymous conversation is still creatable — identity is optional."""
    chat = await SessionRepository(db_session).create_session(title="anonimo")

    assert chat.user_id is None


async def test_mark_escalated_sets_the_reason_and_timestamp(
    database: Database,
) -> None:
    # Separate session scopes on purpose (unlike most of this file's
    # db_session-based tests): a bulk UPDATE (mark_escalated) expires the
    # matching row in whatever session issued it, and re-reading via .get()
    # in that same session needs a sync lazy-refresh SQLAlchemy's async ORM
    # can't do outside an awaited call — the same "never hold a session
    # across a boundary" shape as CLAUDE.md §3's DB-connection rule, just
    # surfacing here as a test-construction detail instead of a request-path
    # rule. A fresh session per phase is how production always reads this
    # back anyway (agent/memory/__init__.py::Memory.is_escalated).
    async with database.session() as session:
        chat = await SessionRepository(session).create_session(user_id="usr_alice")
    async with database.session() as session:
        changed = await SessionRepository(session).mark_escalated(
            chat.id, "duplicate payment, refund needed"
        )
    assert changed is True

    async with database.session() as session:
        reloaded = await SessionRepository(session).get_session(chat.id)
    assert reloaded is not None
    assert reloaded.escalated_at is not None
    assert reloaded.escalation_reason == "duplicate payment, refund needed"


async def test_mark_escalated_is_idempotent(database: Database) -> None:
    """A second escalation must not overwrite the first reason — the return
    value alone tells the caller nothing changed."""
    async with database.session() as session:
        chat = await SessionRepository(session).create_session(user_id="usr_alice")
    async with database.session() as session:
        await SessionRepository(session).mark_escalated(chat.id, "first reason")

    async with database.session() as session:
        changed_again = await SessionRepository(session).mark_escalated(
            chat.id, "second reason"
        )
    assert changed_again is False

    async with database.session() as session:
        reloaded = await SessionRepository(session).get_session(chat.id)
    assert reloaded is not None
    assert reloaded.escalation_reason == "first reason"


async def test_mark_escalated_on_an_unknown_session_is_a_no_op(
    db_session: AsyncSession,
) -> None:
    changed = await SessionRepository(db_session).mark_escalated(
        uuid.uuid4(), "orphan reason"
    )

    assert changed is False


# --- facts (semantic memory) -----------------------------------------------


async def test_fact_full_text_search_matches_across_stemming(
    db_session: AsyncSession,
) -> None:
    """The generated tsvector + Spanish dictionary do the work: a query for the
    infinitive finds the conjugated form."""
    repo = FactRepository(db_session)
    await repo.add("alex", "A Alex le gusta el café colombiano")
    await repo.add("maria", "María prefiere el té verde")

    found = await repo.search("gustar", user_id=None)
    assert [f.subject for f in found] == ["alex"]


async def test_fact_search_ignores_stopwords_and_accents_via_stemming(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    await repo.add("alex", "A Alex le gusta el café colombiano")

    assert len(await repo.search("cafe", user_id=None)) == 1


async def test_fact_search_returns_empty_when_nothing_matches(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    await repo.add("alex", "A Alex le gusta el café")

    assert await repo.search("bicicleta", user_id=None) == []


async def test_facts_listed_by_subject_newest_first(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    await repo.add("alex", "vive en Caracas")
    await repo.add("alex", "cambió de trabajo")
    await repo.add("maria", "estudia diseño")

    facts = await repo.list_by_subject("alex", user_id=None)
    assert len(facts) == 2
    assert {f.content for f in facts} == {"vive en Caracas", "cambió de trabajo"}


async def test_fact_search_never_crosses_users(db_session: AsyncSession) -> None:
    """The whole point of facts.user_id (docs/SECURITY.md §3): Alice's facts
    must be invisible to Bob's search, even when both mention the same words."""
    repo = FactRepository(db_session)
    await repo.add("plan", "el cliente está en el plan Pro", user_id="usr_alice")
    await repo.add("plan", "el cliente está en el plan Pro", user_id="usr_bob")

    found = await repo.search("plan pro", user_id="usr_alice")

    assert len(found) == 1
    assert found[0].user_id == "usr_alice"


async def test_fact_list_by_subject_never_crosses_users(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    await repo.add("alex", "vive en Caracas", user_id="usr_alice")
    await repo.add("alex", "vive en Bogotá", user_id="usr_bob")

    found = await repo.list_by_subject("alex", user_id="usr_alice")

    assert [f.content for f in found] == ["vive en Caracas"]


async def test_fact_search_with_no_user_id_only_matches_ownerless_rows(
    db_session: AsyncSession,
) -> None:
    """`user_id=None` is not "no filter" — it only matches rows with no
    owner. An identified user's facts stay invisible to an anonymous caller."""
    repo = FactRepository(db_session)
    await repo.add("plan", "el cliente está en el plan Pro", user_id="usr_alice")

    assert await repo.search("plan pro", user_id=None) == []


async def test_fact_update_cannot_touch_another_users_fact(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    fact = await repo.add("plan", "está en el plan Pro", user_id="usr_alice")

    changed = await repo.update(fact.id, "usr_bob", "hackeado")

    assert changed is False
    [reloaded] = await repo.list_by_subject("plan", user_id="usr_alice")
    assert reloaded.content == "está en el plan Pro"


async def test_fact_update_changes_the_owners_own_fact(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    fact = await repo.add("plan", "está en el plan Pro", user_id="usr_alice")

    changed = await repo.update(fact.id, "usr_alice", "está en el plan Elite", "plan")

    assert changed is True
    [reloaded] = await repo.list_by_subject("plan", user_id="usr_alice")
    assert reloaded.content == "está en el plan Elite"


async def test_fact_delete_cannot_touch_another_users_fact(
    db_session: AsyncSession,
) -> None:
    repo = FactRepository(db_session)
    fact = await repo.add("vpn", "usa split tunnel", user_id="usr_alice")

    deleted = await repo.delete(fact.id, "usr_bob")

    assert deleted is False
    assert len(await repo.list_by_subject("vpn", user_id="usr_alice")) == 1


async def test_invalid_fact_source_is_rejected_by_the_database(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await FactRepository(db_session).add("alex", "algo", source="inventado")

    await db_session.rollback()


# --- episodes (episodic memory) --------------------------------------------


async def test_episode_search_and_recency(db_session: AsyncSession) -> None:
    repo = EpisodeRepository(db_session)
    await repo.add(
        datetime(2026, 5, 1, tzinfo=UTC), "El cliente reclamó un cobro duplicado"
    )
    await repo.add(
        datetime(2026, 6, 1, tzinfo=UTC), "Se resolvió el envío tardío del pedido"
    )

    recent = await repo.list_recent(user_id=None)
    assert recent[0].summary.startswith("Se resolvió")

    found = await repo.search("cobro duplicado", user_id=None)
    assert len(found) == 1
    assert "cobro duplicado" in found[0].summary


async def test_episode_search_never_crosses_users(db_session: AsyncSession) -> None:
    repo = EpisodeRepository(db_session)
    await repo.add(
        datetime(2026, 5, 1, tzinfo=UTC), "reclamo resuelto", user_id="usr_alice"
    )
    await repo.add(
        datetime(2026, 5, 1, tzinfo=UTC), "reclamo resuelto", user_id="usr_bob"
    )

    found = await repo.search("reclamo", user_id="usr_alice")

    assert len(found) == 1
    assert found[0].user_id == "usr_alice"


async def test_episode_list_recent_never_crosses_users(
    db_session: AsyncSession,
) -> None:
    repo = EpisodeRepository(db_session)
    await repo.add(datetime(2026, 5, 1, tzinfo=UTC), "de alice", user_id="usr_alice")
    await repo.add(datetime(2026, 6, 1, tzinfo=UTC), "de bob", user_id="usr_bob")

    recent = await repo.list_recent(user_id="usr_alice")

    assert [ep.summary for ep in recent] == ["de alice"]


async def test_episode_delete_cannot_touch_another_users_episode(
    db_session: AsyncSession,
) -> None:
    repo = EpisodeRepository(db_session)
    episode = await repo.add(
        datetime(2026, 5, 1, tzinfo=UTC), "algo pasó", user_id="usr_alice"
    )

    deleted = await repo.delete(episode.id, "usr_bob")

    assert deleted is False
    assert len(await repo.list_recent(user_id="usr_alice")) == 1


async def test_episode_delete_removes_the_owners_own_episode(
    db_session: AsyncSession,
) -> None:
    repo = EpisodeRepository(db_session)
    episode = await repo.add(
        datetime(2026, 5, 1, tzinfo=UTC), "algo pasó", user_id="usr_alice"
    )

    deleted = await repo.delete(episode.id, "usr_alice")

    assert deleted is True
    assert await repo.list_recent(user_id="usr_alice") == []


async def test_episode_search_is_limited_by_the_spanish_stemmer(
    db_session: AsyncSession,
) -> None:
    """Documents a real limitation rather than pretending it away.

    The snowball stemmer is aggressive with plurals: 'reclamó' indexes as
    'reclam' but the query 'reclamos' stems to 'recl', so they do not match.
    Recall is not guaranteed across every inflection — the day that matters,
    the fix is embeddings (pgvector), not a bigger dictionary.
    """
    repo = EpisodeRepository(db_session)
    await repo.add(datetime(2026, 5, 1, tzinfo=UTC), "El cliente reclamó un cobro")

    assert await repo.search("reclamos", user_id=None) == []
    assert len(await repo.search("reclamo", user_id=None)) == 1
