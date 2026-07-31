"""Offline harness for ``respond()`` tests — mirrors Waku's ``evals/helpers.py``.

A scripted, async stand-in for the LLM plus a ``make_agent`` factory, so a whole
turn runs deterministically against the real test Postgres without ever calling
Anthropic. See ``tests/integration/README.md`` for the why.

Two deliberate departures from Waku's helpers (documented there too):

- **Real ``anthropic.types`` objects, not ``SimpleNamespace``.** Our ``run_loop``
  narrows blocks with ``isinstance(b, ToolUseBlock)`` / ``isinstance(b, TextBlock)``
  (SDK types at the boundary), so a duck-typed fake would be mis-read.
- **Async client.** Ours is ``AsyncAnthropic`` (``await messages.create``), so the
  scripted client's ``create`` is a coroutine.

The one shared client answers both the retrieval gate and the loop, so a script
is ``[gate_response, *loop_responses]`` — exactly Waku's ordering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from agent.app import Agent, build_agent
from agent.memory.db import Database
from agent.tools.registry import ToolRegistry

_StopReason = Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]


def text_block(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def tool_block(name: str, args: dict[str, Any], call_id: str = "tu_1") -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=call_id, name=name, input=args)


def response(
    blocks: list[Any],
    stop_reason: _StopReason = "end_turn",
    *,
    in_tokens: int = 0,
    out_tokens: int = 0,
) -> Message:
    """A canned assistant Message — the unit a ScriptedClient plays back."""
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="fake-model",
        content=blocks,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=in_tokens, output_tokens=out_tokens),
    )


class _ScriptedMessages:
    def __init__(self, script: list[Message]) -> None:
        self._script = script

    async def create(self, **kwargs: Any) -> Message:
        if not self._script:
            raise AssertionError("ScriptedClient ran out of scripted responses")
        return self._script.pop(0)


class ScriptedClient:
    """Async stand-in for ``AsyncAnthropic``: plays back a fixed list of Messages.

    Deliberately exposes no ``stream`` attribute — ``run_loop`` gates streaming on
    ``hasattr(client.messages, "stream")``, so this always takes the plain
    ``create`` path (the tests drive ``respond(stream=False)``).
    """

    def __init__(self, script: list[Message]) -> None:
        self.messages = _ScriptedMessages(list(script))


def make_agent(
    db: Database,
    client: Any,
    *,
    tools: ToolRegistry | None = None,
    chat_model: str = "fake-chat-model",
    fast_model: str = "fake-fast-model",
    trace_dir: Path | None = None,
) -> Agent:
    """Assemble a wired ``Agent`` over the test DB with a fake model injected.

    Mirrors Waku's ``make_waku``: calls the very same ``build_agent`` factory the
    transport lifespan uses, but with the scripted client, no embedder (semantic
    memory degrades to full-text search — fine offline) and, by default, no trace
    dir (stdout-only). Sharing the factory is the point: the harness can't drift
    from how production assembles the Agent.

    Pass ``trace_dir`` (a tmp_path) to assert on what a turn actually wrote.
    """
    return build_agent(
        client=client,
        db=db,
        tools=tools or ToolRegistry(),
        chat_model=chat_model,
        fast_model=fast_model,
        trace_dir=trace_dir,
    )
