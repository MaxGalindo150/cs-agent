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
from agent.tools.implementations.present_choice import make_present_choice_tool
from agent.tools.registry import Tool, ToolRegistry
from agent.vision import Image
from integration.helpers import (
    ScriptedClient,
    make_agent,
    response,
    text_block,
    tool_block,
)

_SKIP_GATE = text_block('{"retrieve": false, "query": "", "reason": "test"}')
_CHOICE_OPTIONS = [
    {"id": "card", "label": "Reembolso a tarjeta"},
    {"id": "credit", "label": "Crédito en la tienda"},
]


def _present_choice_registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(make_present_choice_tool())
    return tools


async def _suspended_tool_use(
    database: Database, session_id: uuid.UUID
) -> dict[str, Any] | None:
    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
    assert row is not None
    return row.suspended_tool_use


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
    assert result.needs_human is False
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
            response(
                [text_block('{"retrieve": false, "query": "", "reason": "test"}')]
            ),
            response([text_block("¿Algo más en lo que te ayude?")]),
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

    # A second turn: the reloaded history must carry the marker text, never
    # replay the image itself (agent/app.py's whole reason for the marker).
    await agent.respond(session_id, "gracias, eso es todo")

    second_loop_call = client.messages.calls[3]
    history_content = [m["content"] for m in second_loop_call["messages"]]
    assert "aquí está mi comprobante\n[1 image attached]" in history_content
    assert not any(
        isinstance(c, list) and any(b.get("type") == "image" for b in c)
        for c in history_content
    )


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
    assert result.needs_human is True


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


# --- suspended tool calls (present_choice) ----------------------------------


async def test_present_choice_suspends_and_persists_resumable_state(
    database: Database,
) -> None:
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                    )
                ],
                "tool_use",
            ),
        ]
    )
    agent = make_agent(database, client, tools=_present_choice_registry())
    session_id = await _new_session(database)

    result = await agent.respond(session_id, "quiero mi reembolso")

    assert result.reply == "¿Cómo prefieres?"
    meta = await _assistant_meta(database, session_id)
    assert meta is not None
    assert meta["segments"][-1] == {
        "type": "choice",
        "prompt": "¿Cómo prefieres?",
        "options": _CHOICE_OPTIONS,
    }

    pending = await _suspended_tool_use(database, session_id)
    assert pending is not None
    assert pending["tool_name"] == "present_choice"
    assert pending["payload"]["options"] == _CHOICE_OPTIONS
    assert pending["system"] is not None
    assert pending["turn_tail"][0] == {"role": "user", "content": "quiero mi reembolso"}


async def test_button_click_resumes_without_rebuilding_the_system_prompt(
    database: Database,
) -> None:
    """Exactly 3 scripted responses total: the gate, the present_choice call,
    and the resumed reply. If the button path mistakenly called
    build_system() again, it would need a 4th (gate) response and
    ScriptedClient would raise "ran out of scripted responses" — the
    strongest proof available that the system prompt was reused verbatim."""
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                    )
                ],
                "tool_use",
            ),
            response([text_block("Listo, reembolsado a tu tarjeta.")]),
        ]
    )
    agent = make_agent(database, client, tools=_present_choice_registry())
    session_id = await _new_session(database)
    await agent.respond(session_id, "quiero mi reembolso")

    result = await agent.respond(session_id, choice_id="card")

    assert result.reply == "Listo, reembolsado a tu tarjeta."
    assert len(client.messages.calls) == 3
    assert await _suspended_tool_use(database, session_id) is None

    # The FIRST assistant row (the half-turn that asked the question) is the
    # one mark_choice_resolved patches — not the second/final row.
    async with database.session() as session:
        messages = await SessionRepository(session).list_messages(session_id)
    assistant_rows = [m for m in messages if m.role == "assistant"]
    assert len(assistant_rows) == 2
    assert assistant_rows[0].meta is not None
    assert assistant_rows[0].meta["segments"][-1]["resolvedOptionId"] == "card"


async def test_free_text_resume_runs_build_system_fresh(database: Database) -> None:
    """The customer types instead of clicking: a real new gate call must run
    (4 scripted responses total, not 3) — this is genuinely new input the
    retrieval gate and skill matcher should see."""
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                    )
                ],
                "tool_use",
            ),
            response([_SKIP_GATE]),
            response([text_block("Entendido, va a tu tarjeta.")]),
        ]
    )
    agent = make_agent(database, client, tools=_present_choice_registry())
    session_id = await _new_session(database)
    await agent.respond(session_id, "quiero mi reembolso")

    result = await agent.respond(session_id, "mejor a mi tarjeta")

    assert result.reply == "Entendido, va a tu tarjeta."
    assert len(client.messages.calls) == 4
    assert await _suspended_tool_use(database, session_id) is None


async def test_stale_choice_id_is_rejected_without_touching_the_suspension(
    database: Database,
) -> None:
    """Only 2 scripted responses: if the stale click were mistakenly treated
    as a resolution, the loop would need a 3rd and ScriptedClient would raise
    — proving no LLM call happened at all for a rejected click."""
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                    )
                ],
                "tool_use",
            ),
        ]
    )
    agent = make_agent(database, client, tools=_present_choice_registry())
    session_id = await _new_session(database)
    await agent.respond(session_id, "quiero mi reembolso")
    pending_before = await _suspended_tool_use(database, session_id)

    result = await agent.respond(session_id, choice_id="not_a_real_option")

    assert "choose one of the options" in result.reply
    assert await _suspended_tool_use(database, session_id) == pending_before


async def test_turn_tail_preserves_an_earlier_tool_call_in_the_same_turn(
    database: Database,
) -> None:
    """Regression: a single-message snapshot would lose this — the model
    called get_order in an earlier iteration, before present_choice in a
    later one, of the SAME turn. Both must survive to the resumed call."""

    async def get_order(order_id: str) -> str:
        return f"order {order_id}: 2 cargos pendientes"

    tools = _present_choice_registry()
    tools.register(
        Tool(
            name="get_order",
            description="d",
            input_schema={
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
            },
            fn=get_order,
        )
    )
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [tool_block("get_order", {"order_id": "7"}, "toolu_order")], "tool_use"
            ),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cuál cargo?", "options": _CHOICE_OPTIONS},
                        "toolu_choice",
                    )
                ],
                "tool_use",
            ),
            response([text_block("Resuelto.")]),
        ]
    )
    agent = make_agent(database, client, tools=tools)
    session_id = await _new_session(database)
    await agent.respond(session_id, "hay 2 cargos en mi orden 7, ayuda")

    await agent.respond(session_id, choice_id="card")

    resume_call = client.messages.calls[-1]
    tool_result_ids = {
        block["tool_use_id"]
        for m in resume_call["messages"]
        if isinstance(m.get("content"), list)
        for block in m["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    }
    assert "toolu_order" in tool_result_ids  # earlier call preserved
    assert "toolu_choice" in tool_result_ids  # this leg's own resolution


async def test_an_image_never_leaks_into_a_suspended_turns_persisted_state(
    database: Database,
) -> None:
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                    )
                ],
                "tool_use",
            ),
        ]
    )
    agent = make_agent(database, client, tools=_present_choice_registry())
    session_id = await _new_session(database)
    image = Image(media_type="image/png", data="aGVsbG8=")

    await agent.respond(session_id, "aquí mi comprobante", images=[image])

    pending = await _suspended_tool_use(database, session_id)
    assert pending is not None
    first_entry_content = pending["turn_tail"][0]["content"]
    assert first_entry_content == "aquí mi comprobante\n[1 image attached]"


async def test_a_malformed_suspended_payload_is_cleared_instead_of_wedging(
    database: Database,
) -> None:
    """A row written by a different (or buggy) version of this code might not
    match SuspendedToolUse's shape. This must degrade to "nothing pending" —
    never a KeyError that leaves the suspension neither claimed nor resumed,
    which would make every later turn in this conversation fail the same way
    forever."""
    session_id = await _new_session(database)
    async with database.session() as session:
        await SessionRepository(session).set_suspended_tool_use(
            session_id, {"tool_use_id": "toolu_1"}
        )
    agent = make_agent(database, ScriptedClient([]))

    result = await agent.respond(session_id, choice_id="card")

    assert "already been answered" in result.reply
    assert await _suspended_tool_use(database, session_id) is None


async def test_resuming_with_no_iteration_budget_left_escalates_to_human(
    database: Database,
) -> None:
    """The suspending call happened in the turn's only allowed iteration —
    resuming would otherwise call run_loop with a non-positive budget and get
    back its generic "iteration limit" reply, silently truncating instead of
    escalating (CLAUDE.md's own budget rule). Only 2 scripted responses: if
    resume mistakenly called the LLM again, ScriptedClient would raise."""
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                    )
                ],
                "tool_use",
            ),
        ]
    )
    agent = make_agent(
        database, client, tools=_present_choice_registry(), max_iterations=1
    )
    session_id = await _new_session(database)
    await agent.respond(session_id, "quiero mi reembolso")

    result = await agent.respond(session_id, choice_id="card")

    assert "agente humano" in result.reply
    assert result.needs_human is True
    async with database.session() as session:
        row = await SessionRepository(session).get_session(session_id)
    assert row is not None
    assert row.escalated_at is not None
    assert await _suspended_tool_use(database, session_id) is None


async def test_a_second_suspension_right_after_the_first_does_not_orphan_a_tool_result(
    database: Database,
) -> None:
    """Regression: asking a SECOND present_choice immediately after the first
    resolves must not carry the first leg's tool_result into the second
    suspension's turn_tail — its matching tool_use never survives into
    session.history (persisted as plain text, not raw blocks), so replaying
    it verbatim on the NEXT resume would leave an orphaned tool_result and the
    API would reject the request with a 400."""
    client = ScriptedClient(
        [
            response([_SKIP_GATE]),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Cómo prefieres?", "options": _CHOICE_OPTIONS},
                        "toolu_a",
                    )
                ],
                "tool_use",
            ),
            response(
                [
                    tool_block(
                        "present_choice",
                        {"prompt": "¿Qué monto?", "options": _CHOICE_OPTIONS},
                        "toolu_b",
                    )
                ],
                "tool_use",
            ),
            response([text_block("Listo.")]),
        ]
    )
    agent = make_agent(database, client, tools=_present_choice_registry())
    session_id = await _new_session(database)
    await agent.respond(session_id, "quiero mi reembolso")

    # Resolving the FIRST choice immediately triggers a SECOND present_choice
    # (the 3rd scripted response) — this turn suspends again.
    first_resume = await agent.respond(session_id, choice_id="card")
    assert first_resume.reply == "¿Qué monto?"

    # Resolving the SECOND choice must not 400 on an orphaned tool_result.
    second_resume = await agent.respond(session_id, choice_id="card")
    assert second_resume.reply == "Listo."

    final_call_messages = client.messages.calls[-1]["messages"]
    tool_use_ids_seen: set[str] = set()
    for m in final_call_messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_use_ids_seen.add(block["id"])
            elif block.get("type") == "tool_result":
                assert block["tool_use_id"] in tool_use_ids_seen, (
                    f"orphaned tool_result for {block['tool_use_id']!r}"
                )
    assert "toolu_b" in tool_use_ids_seen
