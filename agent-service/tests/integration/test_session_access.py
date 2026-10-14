"""Integration tests for session ownership on resume (service/core/session_access.py).

Against the real database, since ownership is the ``user_id`` stamped on the
``chat_sessions`` row at creation.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from agent.identity import Principal
from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from service.core.session_access import SessionAccess


async def _create(database: Database, user_id: str | None) -> uuid.UUID:
    async with database.session() as s:
        return (await SessionRepository(s).create_session(user_id=user_id)).id


@pytest.mark.parametrize(
    ("owner", "caller"),
    [("usr_a", Principal(user_id="usr_a")), (None, None)],
    ids=["same-user", "anonymous-own-session"],
)
async def test_the_starter_may_continue(
    database: Database, owner: str | None, caller: Principal | None
) -> None:
    session_id = await _create(database, owner)

    await SessionAccess(lambda: database).require(session_id, caller)


@pytest.mark.parametrize(
    ("owner", "caller"),
    [
        ("usr_b", Principal(user_id="usr_a")),
        ("usr_b", None),
        (None, Principal(user_id="usr_a")),
    ],
    ids=["other-user", "anonymous-into-signed-in", "signed-in-into-anonymous"],
)
async def test_anyone_else_gets_not_found(
    database: Database, owner: str | None, caller: Principal | None
) -> None:
    session_id = await _create(database, owner)

    with pytest.raises(HTTPException) as exc:
        await SessionAccess(lambda: database).require(session_id, caller)

    assert exc.value.status_code == 404


async def test_unknown_session_is_not_found(database: Database) -> None:
    with pytest.raises(HTTPException) as exc:
        await SessionAccess(lambda: database).require(uuid.uuid4(), None)

    assert exc.value.status_code == 404
