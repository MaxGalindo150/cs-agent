"""Behavioural tests for the memory repositories against a real PostgreSQL.

These assert on rows and on database-enforced behaviour that no mock can prove:
the generated `tsvector` columns, Spanish stemming, the CHECK guards, and the
FK cascade. Deterministic and hermetic — no LLM, no network beyond the DB.
"""

from __future__ import annotations

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
    import uuid

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
