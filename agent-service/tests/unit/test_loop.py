"""Unit tests for the agent loop (Level 1 — deterministic, fake LLM client).

The loop takes `client` as a parameter, so we inject a fake AsyncAnthropic whose
`messages.create` / `messages.stream` return canned objects. Because the loop
narrows content with `isinstance(..., ToolUseBlock / TextBlock)`, the fakes must
be *real* SDK types (pydantic models), not plain dicts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal, cast

import anthropic
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from agent.loop.agent import LoopResult, run_loop
from agent.tools.registry import Tool, ToolRegistry

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


# ---- builders for real SDK objects ---------------------------------------


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _tool_use(name: str, tool_input: dict[str, Any], block_id: str) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=block_id, name=name, input=tool_input)


def _msg(
    *blocks: Any, stop_reason: Literal["end_turn", "tool_use"] = "end_turn"
) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=list(blocks),
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def _register(reg: ToolRegistry, name: str, fn: Callable[..., Awaitable[str]]) -> None:
    reg.register(Tool(name=name, description="d", input_schema=_SCHEMA, fn=fn))


def _run(
    client: object,
    model: str,
    system: str,
    messages: list[Any],
    tools: ToolRegistry,
    **kw: Any,
) -> Awaitable[LoopResult]:
    """Run the loop with a fake client, casting at this single test boundary."""
    return run_loop(
        cast(anthropic.AsyncAnthropic, client), model, system, messages, tools, **kw
    )


# ---- fake client: non-streaming path -------------------------------------


class _FakeMessages:
    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    """Minimal stand-in for AsyncAnthropic (non-streaming path)."""

    def __init__(self, responses: list[Message]) -> None:
        self.messages = _FakeMessages(responses)


# ---- tests: non-streaming -------------------------------------------------


async def test_no_tool_call_returns_text_reply() -> None:
    client = FakeClient([_msg(_text("hello world"))])
    messages: list[Any] = [{"role": "user", "content": "hi"}]

    result = await _run(client, "m", "sys", messages, ToolRegistry())

    assert result.reply == "hello world"
    assert result.iterations == 1
    assert result.tool_calls == []
    # working memory grew by exactly the assistant turn
    assert len(messages) == 2
    assert messages[-1]["role"] == "assistant"


async def test_system_and_model_reach_the_client() -> None:
    client = FakeClient([_msg(_text("ok"))])

    await _run(
        client,
        "my-model",
        "my-system",
        [{"role": "user", "content": "hi"}],
        ToolRegistry(),
    )

    call = client.messages.calls[0]
    assert call["model"] == "my-model"
    assert call["system"] == "my-system"


async def test_tool_call_executes_then_returns_final_text() -> None:
    ran: list[tuple[int, int]] = []

    async def add(a: int, b: int) -> str:
        ran.append((a, b))
        return str(a + b)

    reg = ToolRegistry()
    _register(reg, "add", add)

    client = FakeClient(
        [
            _msg(_tool_use("add", {"a": 2, "b": 3}, "toolu_1"), stop_reason="tool_use"),
            _msg(_text("the answer is 5")),
        ]
    )
    messages: list[Any] = [{"role": "user", "content": "add 2 and 3"}]

    result = await _run(client, "m", "sys", messages, reg)

    assert ran == [(2, 3)]  # the tool actually ran, with parsed args
    assert result.reply == "the answer is 5"
    assert result.iterations == 2
    assert result.tool_calls == [
        {"tool": "add", "args": {"a": 2, "b": 3}, "output": "5"}
    ]
    # wire format: a tool_result user turn was fed back with the matching id
    tool_turn = messages[2]
    assert tool_turn["role"] == "user"
    tool_result = tool_turn["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_1"
    assert tool_result["content"] == "5"


async def test_tool_start_is_announced_before_the_tool_runs() -> None:
    """The UI shows work in progress off ``tool_start``, so it must be emitted
    before execution — not alongside the result, which lands seconds later."""
    events: list[tuple[str, dict[str, Any]]] = []

    async def slow(a: int) -> str:
        # Anything the observer saw by now was emitted before execution.
        events.append(("__executing__", {"a": a}))
        return "ok"

    reg = ToolRegistry()
    _register(reg, "slow", slow)

    client = FakeClient(
        [
            _msg(_tool_use("slow", {"a": 1}, "toolu_1"), stop_reason="tool_use"),
            _msg(_text("done")),
        ]
    )

    await _run(
        client,
        "m",
        "sys",
        [{"role": "user", "content": "go"}],
        reg,
        observer=lambda kind, ev: events.append((kind, ev)),
    )

    kinds = [kind for kind, _ in events]
    assert kinds.index("tool_start") < kinds.index("__executing__")
    assert kinds.index("__executing__") < kinds.index("tool")
    # It carries the tool's own progress label, and never a result (there is
    # none yet) — that is what separates it from the "tool" event.
    start = next(ev for kind, ev in events if kind == "tool_start")
    assert start == {"tool": "slow", "args": {"a": 1}, "label": "slow"}
    assert "output" not in start


async def test_every_tool_in_a_batch_is_announced() -> None:
    """Tools run concurrently, so N starts precede the N results."""
    events: list[tuple[str, dict[str, Any]]] = []

    async def noop(n: int) -> str:
        return str(n)

    reg = ToolRegistry()
    _register(reg, "noop", noop)

    client = FakeClient(
        [
            _msg(
                _tool_use("noop", {"n": 1}, "toolu_1"),
                _tool_use("noop", {"n": 2}, "toolu_2"),
                stop_reason="tool_use",
            ),
            _msg(_text("done")),
        ]
    )

    await _run(
        client,
        "m",
        "sys",
        [{"role": "user", "content": "go"}],
        reg,
        observer=lambda kind, ev: events.append((kind, ev)),
    )

    kinds = [kind for kind, _ in events]
    assert kinds.count("tool_start") == 2
    assert kinds.count("tool") == 2
    # Both announcements come first — the batch is dispatched as a unit.
    assert kinds.index("tool_start") < kinds.index("tool")
    last_start = len(kinds) - 1 - kinds[::-1].index("tool_start")
    assert last_start < kinds.index("tool")


async def test_hits_iteration_limit_guardrail() -> None:
    async def noop() -> str:
        return "ran"

    reg = ToolRegistry()
    _register(reg, "noop", noop)

    # every response asks for a tool → the loop never ends naturally
    responses = [
        _msg(_tool_use("noop", {}, f"toolu_{i}"), stop_reason="tool_use")
        for i in range(3)
    ]
    client = FakeClient(responses)

    result = await _run(
        client, "m", "sys", [{"role": "user", "content": "spin"}], reg, max_iterations=3
    )

    assert result.iterations == 3
    assert "iteration limit" in result.reply
    assert len(client.messages.calls) == 3


# ---- fake client: streaming path -----------------------------------------


class _FakeStream:
    def __init__(self, deltas: list[str], final: Message) -> None:
        self._deltas = deltas
        self._final = final

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            for delta in self._deltas:
                yield delta

        return _gen()

    async def get_final_message(self) -> Message:
        return self._final


class _StreamingMessages:
    def __init__(self, deltas: list[str], final: Message) -> None:
        self._deltas = deltas
        self._final = final

    def stream(self, **kwargs: Any) -> _FakeStream:
        return _FakeStream(self._deltas, self._final)


class StreamingClient:
    def __init__(self, deltas: list[str], final: Message) -> None:
        self.messages = _StreamingMessages(deltas, final)


async def test_streaming_emits_deltas_and_returns_final_text() -> None:
    client = StreamingClient(["hel", "lo ", "world"], _msg(_text("hello world")))
    seen: list[str] = []

    def observer(kind: str, event: dict[str, Any]) -> None:
        if kind == "text":
            seen.append(event["delta"])

    result = await _run(
        client,
        "m",
        "sys",
        [{"role": "user", "content": "hi"}],
        ToolRegistry(),
        observer=observer,
        stream=True,
    )

    assert seen == ["hel", "lo ", "world"]
    assert result.reply == "hello world"
    assert result.iterations == 1


# ---- fake client: streaming failure → fallback to create ------------------


class _BoomStream:
    async def __aenter__(self) -> _BoomStream:
        # Network-style failure: the kind of error a stream fallback should
        # recover from. RuntimeError and friends would be real bugs and must
        # propagate, not be swallowed.
        raise ConnectionError("stream down")

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FallbackMessages:
    def __init__(self, final: Message) -> None:
        self._final = final
        self.create_calls = 0

    def stream(self, **kwargs: Any) -> _BoomStream:
        return _BoomStream()

    async def create(self, **kwargs: Any) -> Message:
        self.create_calls += 1
        return self._final


class FallbackClient:
    def __init__(self, final: Message) -> None:
        self.messages = _FallbackMessages(final)


async def test_streaming_failure_falls_back_to_create() -> None:
    client = FallbackClient(_msg(_text("fallback reply")))
    events: list[tuple[str, dict[str, Any]]] = []

    result = await _run(
        client,
        "m",
        "sys",
        [{"role": "user", "content": "hi"}],
        ToolRegistry(),
        stream=True,
        observer=lambda kind, ev: events.append((kind, ev)),
    )

    assert result.reply == "fallback reply"
    assert client.messages.create_calls == 1
    # The hiccup must be observable, not swallowed silently.
    assert any(kind == "stream_error" for kind, _ in events)
