"""Integration tests for the decision sites across a whole turn — real
Postgres, scripted LLM, scripted decider.

What the unit tests can't see: that the judge's scores land in the trace
keyed by the persisted message id, that the turn's meta records which
decisions were made, that an unsure judge escalates to the LLM judge, and
that a thumbs-down through the HTTP route produces a feedback score and a
diagnosis.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent.decide.fake import FakeDecider, choice, noul, score
from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from agent.tools.registry import Tool, ToolRegistry
from integration.helpers import (
    ScriptedClient,
    make_agent,
    response,
    text_block,
    tool_block,
)
from service.core.agent import get_agent_optional, get_database
from service.main import create_app

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"order_number": {"type": "string"}},
}


def _ledger(trace_dir: Path, name: str) -> list[dict[str, Any]]:
    path = trace_dir / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


async def _new_session(database: Database, user_id: str | None = None) -> uuid.UUID:
    async with database.session() as session:
        row = await SessionRepository(session).create_session(user_id=user_id)
    return row.id


async def _assistant(database: Database, session_id: uuid.UUID) -> Any:
    async with database.session() as session:
        messages = await SessionRepository(session).list_messages(session_id)
    return [m for m in messages if m.role == "assistant"][-1]


def _tools() -> ToolRegistry:
    async def get_order_detail(order_number: str = "") -> str:
        return f"order {order_number}: in progress"

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="get_order_detail",
            description="one order",
            input_schema=_SCHEMA,
            fn=get_order_detail,
        )
    )
    return tools


def _gate(retrieve: bool = False) -> dict[str, Any]:
    return {
        "needs_history": noul(0.9 if retrieve else 0.1),
        "memory_kind": choice("facts", 0.9),
    }


def _no_skill() -> dict[str, Any]:
    return {"skill": choice("none", 0.95)}


def _fit(tool: str) -> dict[str, Any]:
    return {"fits": noul(0.95), "best_tool": choice(tool, 1.0), "risk": score(0, 1)}


def _judge(quality: int, confidence: float) -> dict[str, Any]:
    return {
        "quality": score(quality, confidence, levels=5),
        "grounded": noul(0.9),
        "resolved": noul(0.8),
    }


async def test_turn_scores_land_in_the_ledger_keyed_by_the_message(
    database: Database, tmp_path: Path
) -> None:
    # no skills dir for "consumer" in the test tree → skill_match is skipped
    fake = (
        FakeDecider()
        .script(_gate())
        .script(_fit("get_order_detail"))
        .script(_judge(3, 0.95))
    )
    client = ScriptedClient(
        [
            response(
                [tool_block("get_order_detail", {"order_number": "924141"})], "tool_use"
            ),
            response([text_block("La 924141 está en progreso.")]),
        ]
    )
    agent = make_agent(
        database, client, tools=_tools(), trace_dir=tmp_path, decider=fake
    )
    session_id = await _new_session(database)

    result = await agent.respond(session_id, "detalle de la 924141")

    assert result.message_id is not None
    scores = _ledger(tmp_path, "scores.jsonl")
    assert {s["name"]: s["value"] for s in scores} == {
        "jev.quality": 3.0,
        "jev.grounded": True,
        "jev.resolved": True,
    }
    assert {s["message_id"] for s in scores} == {str(result.message_id)}
    assert {s["session_id"] for s in scores} == {str(session_id)}
    decisions = _ledger(tmp_path, "decisions.jsonl")
    assert [d["site"] for d in decisions] == ["retrieval", "tool_review", "judge"]
    # the Haiku gate was never called: the scripted client only had loop turns
    assert client.messages.calls[0]["messages"][-1]["content"] == "detalle de la 924141"

    row = await _assistant(database, session_id)
    meta = row.meta
    assert meta["gate"] == {"decision": "skip", "reason": "jev p=0.10"}
    assert [d["site"] for d in meta["decisions"]] == ["retrieval", "tool_review"]
    assert meta["nudges"] == [] and meta["budget_exhausted"] is None
    assert meta["skills"] == []


async def test_unsure_judge_escalates_to_the_llm_judge(
    database: Database, tmp_path: Path
) -> None:
    fake = FakeDecider().script(_gate()).script(_judge(2, 0.5))
    client = ScriptedClient(
        [
            response([text_block("Hola, ¿en qué te ayudo?")]),
            # the LLM judge's verdict, the next thing the client is asked
            response(
                [
                    text_block(
                        '{"quality": 3, "grounded": true, "resolved": false, '
                        '"reason": "fine greeting"}'
                    )
                ]
            ),
        ]
    )
    agent = make_agent(database, client, trace_dir=tmp_path, decider=fake)
    session_id = await _new_session(database)

    await agent.respond(session_id, "hola")

    scores = {s["name"]: s for s in _ledger(tmp_path, "scores.jsonl")}
    assert scores["jev.quality"]["value"] == 2.0
    assert scores["llm.quality"]["value"] == 3.0
    assert scores["llm.quality"]["source"] == "llm"
    assert scores["llm.resolved"]["value"] is False
    judge_call = client.messages.calls[1]
    assert judge_call["model"] == "fake-fast-model"
    assert "Hola, ¿en qué te ayudo?" in judge_call["messages"][0]["content"]


async def test_a_failing_judge_never_fails_the_turn(
    database: Database, tmp_path: Path
) -> None:
    fake = FakeDecider().script(_gate()).fail(500)
    client = ScriptedClient([response([text_block("ok")])])
    agent = make_agent(database, client, trace_dir=tmp_path, decider=fake)
    session_id = await _new_session(database)

    result = await agent.respond(session_id, "hola")

    assert result.reply == "ok" and result.message_id is not None
    assert _ledger(tmp_path, "scores.jsonl") == []
    judge = [d for d in _ledger(tmp_path, "decisions.jsonl") if d["site"] == "judge"]
    assert judge[0]["source"] == "fallback"


async def test_tool_call_budget_is_recorded_on_the_turn(
    database: Database, tmp_path: Path
) -> None:
    # no decider here → the Haiku gate is the first scripted response
    client = ScriptedClient(
        [
            response([text_block('{"retrieve": false, "query": "", "reason": "t"}')]),
            response(
                [
                    tool_block("get_order_detail", {"order_number": "1"}, "a"),
                    tool_block("get_order_detail", {"order_number": "2"}, "b"),
                ],
                "tool_use",
            ),
        ]
    )
    agent = make_agent(
        database, client, tools=_tools(), trace_dir=tmp_path, max_tool_calls=1
    )
    session_id = await _new_session(database)

    result = await agent.respond(session_id, "dos órdenes")

    assert result.budget_exhausted == "tool_calls"
    row = await _assistant(database, session_id)
    assert row.meta["budget_exhausted"] == "tool_calls"
    assert row.meta["tools"] == []


# ---- feedback → score + diagnosis -------------------------------------------------


@pytest.fixture
async def feedback_api(
    database: Database, tmp_path: Path
) -> AsyncIterator[tuple[httpx.AsyncClient, FakeDecider, Path]]:
    fake = FakeDecider()
    agent = make_agent(database, ScriptedClient([]), trace_dir=tmp_path, decider=fake)
    app = create_app()
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_agent_optional] = lambda: agent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake, tmp_path


async def _thread(database: Database) -> tuple[uuid.UUID, uuid.UUID]:
    async with database.session() as s:
        repo = SessionRepository(s)
        session_id = (await repo.create_session(title="hilo", user_id="usr_a")).id
        await repo.append_message(session_id, "user", "¿mis órdenes?")
        reply = await repo.append_message(
            session_id,
            "assistant",
            "aquí están",
            meta={"tools": [{"tool": "search_orders", "status": "ok"}], "skills": []},
        )
    return session_id, reply.id


async def test_thumbs_down_records_feedback_and_a_diagnosis(
    feedback_api: tuple[httpx.AsyncClient, FakeDecider, Path], database: Database
) -> None:
    api, fake, trace_dir = feedback_api
    fake.script({"failure_site": choice("tool_choice", 0.9), "actionable": noul(0.8)})
    session_id, reply_id = await _thread(database)

    resp = await api.put(
        f"/v1/sessions/{session_id}/messages/{reply_id}/feedback",
        json={"rating": "down", "comment": "no era eso"},
        headers={"X-User-Id": "usr_a"},
    )

    assert resp.status_code == 204
    scores = {s["name"]: s for s in _ledger(trace_dir, "scores.jsonl")}
    assert scores["user_feedback"]["value"] == -1
    assert scores["user_feedback"]["comment"] == "no era eso"
    assert scores["user_feedback"]["session_id"] == str(session_id)
    assert scores["jev.diagnosis"]["value"] == "tool_choice"
    assert scores["jev.actionable"]["value"] is True
    assert {s["message_id"] for s in scores.values()} == {str(reply_id)}
    state, _ = fake.calls[0]
    assert isinstance(state, dict)
    assert state["user_message"] == "¿mis órdenes?"
    assert state["user_comment"] == "no era eso"
    diagnosis = [
        d for d in _ledger(trace_dir, "decisions.jsonl") if d["site"] == "diagnose"
    ]
    assert diagnosis[0]["message_id"] == str(reply_id)


async def test_thumbs_up_records_feedback_only(
    feedback_api: tuple[httpx.AsyncClient, FakeDecider, Path], database: Database
) -> None:
    api, fake, trace_dir = feedback_api
    session_id, reply_id = await _thread(database)

    resp = await api.put(
        f"/v1/sessions/{session_id}/messages/{reply_id}/feedback",
        json={"rating": "up"},
        headers={"X-User-Id": "usr_a"},
    )

    assert resp.status_code == 204
    assert [s["name"] for s in _ledger(trace_dir, "scores.jsonl")] == ["user_feedback"]
    assert fake.calls == []
