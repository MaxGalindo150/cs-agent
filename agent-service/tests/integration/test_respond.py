"""Integration tests for ``respond()`` — the turn orchestrator against a real DB.

Ported from Waku's ``test_turn_meta``: the assistant row carries a ``meta`` JSON so
a reopened thread renders the full turn card (gate decision, iterations, latency,
tools, model/provider) — not just the text. The LLM is scripted (offline,
deterministic); Postgres is real (the thing under test). See ``helpers.py`` /
``README.md``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from agent.identity import Principal
from agent.memory.db import Database
from agent.memory.repositories import SessionRepository
from agent.tools.registry import Tool, ToolRegistry
from agent.vision import Image
from integration.helpers import (
    ScriptedClient,
    make_agent,
    response,
    text_block,
    tool_block,
)

_ORDER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"order_id": {"type": "string"}},
    "required": ["order_id"],
}


async def _new_session(database: Database) -> uuid.UUID:
    """A committed chat_sessions row — chat_messages FKs to it, so respond()'s
    persistence needs it to exist first (the transport owns this in production)."""
    async with database.session() as session:
        row = await SessionRepository(session).create_session()
    return row.id


async def _assistant_meta(
    database: Database, session_id: uuid.UUID
) -> dict[str, Any] | None:
    async with database.session() as session:
        messages = await SessionRepository(session).list_messages(session_id)
    assistant = [m for m in messages if m.role == "assistant"][-1]
    return assistant.meta


async def test_turn_meta_is_saved_with_gate_iterations_and_tools(
    database: Database,
) -> None:
    async def lookup_order(order_id: str) -> str:
        return f"order {order_id}: delivered"

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="lookup_order",
            description="look up an order by id",
            input_schema=_ORDER_SCHEMA,
            fn=lookup_order,
        )
    )
    # script = [gate, then the loop's turn]: a tool call, then the final answer.
    client = ScriptedClient(
        [
            response(
                [
                    text_block(
                        '{"retrieve": true, "query": "order 7", '
                        '"reason": "asks about order"}'
                    )
                ]
            ),
            response([tool_block("lookup_order", {"order_id": "7"})], "tool_use"),
            response([text_block("Tu orden 7 fue entregada.")]),
        ]
    )
    agent = make_agent(database, client, tools=tools)
    session_id = await _new_session(database)

    await agent.respond(session_id, "¿dónde está mi orden 7?")

    meta = await _assistant_meta(database, session_id)
    assert meta is not None
    assert meta["gate"]["decision"] == "retrieve"
    assert meta["iterations"] == 2  # the tool turn + the final answer
    assert isinstance(meta["latency_ms"], int)
    assert [t["tool"] for t in meta["tools"]] == ["lookup_order"]
    assert meta["model"] == "fake-chat-model"
    assert meta["provider"] == "anthropic"


async def test_a_turn_binds_every_trace_record_to_its_session(
    database: Database, tmp_path: Path
) -> None:
    """End-to-end wiring: the unit tests prove the Tracer *can* stamp a session;
    this proves ``respond()`` actually hands it the id it holds (CLAUDE.md §2.4 —
    every event under a trace id bound to the conversation)."""
    client = ScriptedClient(
        [
            response(
                [text_block('{"retrieve": false, "query": "", "reason": "greeting"}')]
            ),
            response([text_block("¡Hola!")], in_tokens=11, out_tokens=3),
        ]
    )
    agent = make_agent(database, client, trace_dir=tmp_path)
    session_id = await _new_session(database)

    await agent.respond(session_id, "hola")

    traces = [
        json.loads(line)
        for f in tmp_path.glob("*.jsonl")
        if f.name != "usage.jsonl"
        for line in f.read_text().splitlines()
    ]
    assert [t["type"] for t in traces] == ["turn_start", "gate", "llm", "turn_end"]
    assert {t["session_id"] for t in traces} == {str(session_id)}
    assert len({t["turn_id"] for t in traces}) == 1

    # The spend ledger is attributed too, so cost can be read per conversation.
    usage = [
        json.loads(line) for line in (tmp_path / "usage.jsonl").read_text().splitlines()
    ]
    assert [u["session_id"] for u in usage] == [str(session_id)]


async def test_no_tool_turn_still_saves_meta(database: Database) -> None:
    client = ScriptedClient(
        [
            response(
                [text_block('{"retrieve": false, "query": "", "reason": "greeting"}')]
            ),
            response([text_block("¡Hola! ¿En qué te ayudo?")]),
        ]
    )
    agent = make_agent(database, client)
    session_id = await _new_session(database)

    result = await agent.respond(session_id, "hola")

    assert "Hola" in result.reply
    meta = await _assistant_meta(database, session_id)
    assert meta is not None
    assert meta["gate"]["decision"] == "skip"
    assert meta["tools"] == []


async def test_start_session_persists_the_resolved_principals_user_id(
    database: Database,
) -> None:
    """`Agent.start_session` unwraps `Principal` to a plain `user_id` before
    handing it to the memory facade — this is that seam, proven end to end."""
    agent = make_agent(database, ScriptedClient([]))

    session_id = await agent.start_session(
        "soporte", principal=Principal(user_id="usr_0001", email="alice@example.com")
    )

    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
    assert row is not None
    assert row.user_id == "usr_0001"


async def test_start_session_without_a_principal_leaves_user_id_null(
    database: Database,
) -> None:
    agent = make_agent(database, ScriptedClient([]))

    session_id = await agent.start_session("anonimo")

    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
    assert row is not None
    assert row.user_id is None


async def test_meta_carries_the_ordered_text_and_tool_segments(
    database: Database,
) -> None:
    """A client reloading this thread needs to know WHERE the tool call sat
    relative to the two sentences, not just that it happened — that's what
    `meta["segments"]` is for (frontend/src/lib/chat/types.ts::MessagePart)."""

    async def lookup_order(order_id: str) -> str:
        return f"order {order_id}: delivered"

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="lookup_order",
            description="look up an order by id",
            input_schema=_ORDER_SCHEMA,
            fn=lookup_order,
        )
    )
    client = ScriptedClient(
        [
            response(
                [text_block('{"retrieve": false, "query": "", "reason": "test"}')]
            ),
            response(
                [
                    text_block("Let me check that."),
                    tool_block("lookup_order", {"order_id": "7"}),
                ],
                "tool_use",
            ),
            response([text_block("It was delivered.")]),
        ]
    )
    agent = make_agent(database, client, tools=tools)
    session_id = await _new_session(database)

    await agent.respond(session_id, "where is order 7?")

    meta = await _assistant_meta(database, session_id)
    assert meta is not None
    assert meta["segments"] == [
        {"type": "text", "text": "Let me check that."},
        {
            "type": "tools",
            "calls": [
                {
                    "tool": "lookup_order",
                    "args": {"order_id": "7"},
                    "output": "order 7: delivered",
                    "label": "lookup order",
                }
            ],
        },
        {"type": "text", "text": "It was delivered."},
    ]


async def test_an_image_reaches_the_llm_but_never_gets_persisted_raw(
    database: Database,
) -> None:
    """The image must reach the model's content blocks for THIS call, but
    never the persisted row nor a later turn's replayed history — only a
    short marker does (agent/app.py::_user_content / _with_image_marker)."""
    client = ScriptedClient(
        [
            response(
                [text_block('{"retrieve": false, "query": "", "reason": "test"}')]
            ),
            response([text_block("Veo el comprobante, gracias.")]),
        ]
    )
    agent = make_agent(database, client)
    session_id = await _new_session(database)
    image = Image(media_type="image/png", data="aGVsbG8=")

    await agent.respond(session_id, "aquí está mi comprobante", images=[image])

    # The loop's main call (index 1 — index 0 is the retrieval gate) carries
    # the image block alongside the text, as the turn's last message.
    loop_call = client.messages.calls[1]
    last_message = loop_call["messages"][-1]
    assert last_message["role"] == "user"
    assert last_message["content"] == [
        {"type": "text", "text": "aquí está mi comprobante"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "aGVsbG8=",
            },
        },
    ]

    async with database.session() as session:
        messages = await SessionRepository(session).list_messages(session_id)
    user_row = next(m for m in messages if m.role == "user")
    assert user_row.content == "aquí está mi comprobante\n[1 image attached]"


async def test_an_escalated_session_short_circuits_the_llm_entirely(
    database: Database,
) -> None:
    """Once escalated, respond() must never call the LLM again — a canned
    reply goes out instead, so the model can never repeat a promise it can't
    back (agent/runtime/session.py::Session.fixed_response). ScriptedClient([])
    would raise "ran out of scripted responses" if the loop ran at all."""
    session_id = await _new_session(database)
    async with database.session() as session:
        await SessionRepository(session).mark_escalated(session_id, "test reason")
    agent = make_agent(database, ScriptedClient([]))

    result = await agent.respond(session_id, "¿ya me reembolsaron?")

    assert result.iterations == 0
    assert result.tool_calls == []
    assert "human agent" in result.reply.lower()


async def test_an_escalated_sessions_message_is_still_persisted(
    database: Database,
) -> None:
    """The human agent needs the full transcript — the short-circuit skips
    the LLM, never the persistence of what the customer actually said."""
    session_id = await _new_session(database)
    async with database.session() as session:
        await SessionRepository(session).mark_escalated(session_id, "test reason")
    agent = make_agent(database, ScriptedClient([]))

    await agent.respond(session_id, "otro mensaje después de escalar")

    async with database.session() as session:
        messages = await SessionRepository(session).list_messages(session_id)
    contents = [m.content for m in messages if m.role == "user"]
    assert "otro mensaje después de escalar" in contents


async def test_the_escalated_short_circuits_meta_also_carries_a_segment(
    database: Database,
) -> None:
    """The canned reply renders the same way a normal turn's does — a single
    text segment — so the client needs no special case for it."""
    session_id = await _new_session(database)
    async with database.session() as session:
        await SessionRepository(session).mark_escalated(session_id, "test reason")
    agent = make_agent(database, ScriptedClient([]))

    result = await agent.respond(session_id, "¿ya me reembolsaron?")

    meta = await _assistant_meta(database, session_id)
    assert meta is not None
    assert meta["segments"] == [{"type": "text", "text": result.reply}]
