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

from agent.identity import Principal
from agent.loop.agent import LoopResult, _safe_args, run_loop
from agent.tools.context import ToolContext
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


def _register(
    reg: ToolRegistry,
    name: str,
    fn: Callable[..., Awaitable[str]],
    requires_identity: bool = False,
    suspends: bool = False,
) -> None:
    reg.register(
        Tool(
            name=name,
            description="d",
            input_schema=_SCHEMA,
            fn=fn,
            requires_identity=requires_identity,
            suspends=suspends,
        )
    )


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


async def test_sensitive_tool_args_are_redacted_after_execution() -> None:
    received: list[tuple[str, str]] = []
    events: list[tuple[str, dict[str, Any]]] = []

    async def authenticate(security_code: str, phone: str) -> str:
        received.append((security_code, phone))
        return "ok"

    reg = ToolRegistry()
    _register(reg, "authenticate", authenticate)
    client = FakeClient(
        [
            _msg(
                _tool_use(
                    "authenticate",
                    {"security_code": "123456", "phone": "+58 412 123 4567"},
                    "toolu_1",
                ),
                stop_reason="tool_use",
            ),
            _msg(_text("done")),
        ]
    )

    result = await _run(
        client,
        "m",
        "sys",
        [{"role": "user", "content": "go"}],
        reg,
        observer=lambda kind, event: events.append((kind, event)),
    )

    assert received == [("123456", "+58 412 123 4567")]
    expected = {"security_code": "[REDACTED]", "phone": "[REDACTED]"}
    assert result.tool_calls[0]["args"] == expected
    assert next(event for kind, event in events if kind == "tool")["args"] == expected


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


async def test_lead_in_text_before_a_tool_call_becomes_its_own_segment() -> None:
    """Regression: the model can talk before it acts ("Voy a escalar esto...")
    in the same response that asks for a tool. That text must not be dropped
    (it used to be — only the final no-tool-call response set `reply`) nor
    merged with the tool group — it is its own segment, in order, so a client
    can render the tool activity between the two sentences instead of
    hoisting it above both."""

    async def escalate() -> str:
        return "flagged"

    reg = ToolRegistry()
    _register(reg, "escalate_to_human", escalate)

    client = FakeClient(
        [
            _msg(
                _text("Voy a escalar tu solicitud."),
                _tool_use("escalate_to_human", {}, "toolu_1"),
                stop_reason="tool_use",
            ),
            _msg(_text("Listo, ya quedó registrada.")),
        ]
    )

    result = await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg)

    assert result.reply == "Voy a escalar tu solicitud.\n\nListo, ya quedó registrada."
    assert result.segments == [
        {"type": "text", "text": "Voy a escalar tu solicitud."},
        {
            "type": "tools",
            "calls": [
                {
                    "tool": "escalate_to_human",
                    "args": {},
                    "output": "flagged",
                    "label": "escalate to human",
                }
            ],
        },
        {"type": "text", "text": "Listo, ya quedó registrada."},
    ]


async def test_a_tool_only_response_produces_no_empty_lead_in_segment() -> None:
    """The common case (no lead-in text) must not grow a spurious empty text
    segment — only a "tools" segment, exactly like before this feature."""

    async def add(a: int, b: int) -> str:
        return str(a + b)

    reg = ToolRegistry()
    _register(reg, "add", add)

    client = FakeClient(
        [
            _msg(_tool_use("add", {"a": 2, "b": 3}, "toolu_1"), stop_reason="tool_use"),
            _msg(_text("5")),
        ]
    )

    result = await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg)

    assert result.reply == "5"
    assert [seg["type"] for seg in result.segments] == ["tools", "text"]


async def test_suspending_tool_stops_the_loop_without_a_further_llm_call() -> None:
    """`present_choice`'s whole point: once called, the loop must not call the
    LLM again this turn — the model would otherwise have to guess the
    customer's answer instead of actually waiting for it. FakeClient only has
    one scripted response, so a second `create()` call would raise IndexError
    from `.pop(0)` on an empty list — the strongest possible proof here."""

    async def present_choice(prompt: str, options: list[dict[str, str]]) -> str:
        return "paused"

    reg = ToolRegistry()
    _register(reg, "present_choice", present_choice, suspends=True)

    client = FakeClient(
        [
            _msg(
                _tool_use(
                    "present_choice",
                    {
                        "prompt": "Refund to card or store credit?",
                        "options": [
                            {"id": "card", "label": "Card"},
                            {"id": "credit", "label": "Store credit"},
                        ],
                    },
                    "toolu_1",
                ),
                stop_reason="tool_use",
            )
        ]
    )

    result = await _run(
        client, "m", "my-system", [{"role": "user", "content": "hi"}], reg
    )

    assert result.reply == "Refund to card or store credit?"
    assert result.suspended == {
        "tool_use_id": "toolu_1",
        "tool_name": "present_choice",
        "system": "my-system",
        "payload": {
            "prompt": "Refund to card or store credit?",
            "options": [
                {"id": "card", "label": "Card"},
                {"id": "credit", "label": "Store credit"},
            ],
        },
        "iteration": 1,
    }
    assert result.segments == [
        {
            "type": "choice",
            "prompt": "Refund to card or store credit?",
            "options": [
                {"id": "card", "label": "Card"},
                {"id": "credit", "label": "Store credit"},
            ],
        }
    ]


async def test_suspending_tool_emits_a_terminal_tool_event() -> None:
    """`frontend/src/hooks/use-chat.ts` closes a running step only from a
    `tool` event, matched by tool name to the `tool_start` that opened it — a
    suspending call must get one too, or its step stays "running" forever in
    the live transcript."""

    async def present_choice(prompt: str, options: list[dict[str, str]]) -> str:
        return "paused"

    reg = ToolRegistry()
    _register(reg, "present_choice", present_choice, suspends=True)

    client = FakeClient(
        [
            _msg(
                _tool_use("present_choice", {"prompt": "p?", "options": []}, "toolu_1"),
                stop_reason="tool_use",
            )
        ]
    )
    events: list[tuple[str, dict[str, Any]]] = []

    await _run(
        client,
        "m",
        "my-system",
        [{"role": "user", "content": "hi"}],
        reg,
        observer=lambda kind, ev: events.append((kind, ev)),
    )

    kinds = [kind for kind, _ in events]
    assert "tool_start" in kinds
    assert "tool" in kinds
    tool_event = next(ev for kind, ev in events if kind == "tool")
    assert tool_event["tool"] == "present_choice"


async def test_suspending_tool_keeps_lead_in_text_as_its_own_segment() -> None:
    async def present_choice(prompt: str, options: list[dict[str, str]]) -> str:
        return "paused"

    reg = ToolRegistry()
    _register(reg, "present_choice", present_choice, suspends=True)

    client = FakeClient(
        [
            _msg(
                _text("Veo dos pedidos abiertos."),
                _tool_use(
                    "present_choice",
                    {"prompt": "¿Cuál pedido?", "options": [{"id": "a", "label": "A"}]},
                    "toolu_1",
                ),
                stop_reason="tool_use",
            )
        ]
    )

    result = await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg)

    assert result.reply == "Veo dos pedidos abiertos.\n\n¿Cuál pedido?"
    assert result.segments[0] == {"type": "text", "text": "Veo dos pedidos abiertos."}
    assert result.segments[1]["type"] == "choice"


async def test_a_suspending_tool_mixed_with_another_is_refused_not_executed() -> None:
    """Anthropic requires every tool_use in a message to get a tool_result
    before the message list is valid again — a suspending call can't leave
    its batch-mates stranded. Both calls must be refused, and the turn must
    continue (not suspend) so the model can retry alone."""
    ran: list[str] = []

    async def present_choice(prompt: str, options: list[dict[str, str]]) -> str:
        ran.append("present_choice")
        return "should not run"

    async def get_order(order_id: str) -> str:
        ran.append("get_order")
        return "should not run either"

    reg = ToolRegistry()
    _register(reg, "present_choice", present_choice, suspends=True)
    _register(reg, "get_order", get_order)

    client = FakeClient(
        [
            _msg(
                _tool_use("get_order", {"order_id": "7"}, "toolu_1"),
                _tool_use(
                    "present_choice",
                    {"prompt": "p", "options": []},
                    "toolu_2",
                ),
                stop_reason="tool_use",
            ),
            _msg(_text("retried alone")),
        ]
    )

    result = await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg)

    assert ran == []  # neither tool actually executed
    assert result.suspended is None
    assert result.reply == "retried alone"
    calls = result.segments[0]["calls"]
    assert {c["tool"] for c in calls} == {"get_order", "present_choice"}
    assert all("retry it alone" in c["output"] for c in calls)


async def test_ctx_threads_through_to_an_identity_gated_tool() -> None:
    """The loop never inspects ``ctx`` — it only forwards whatever the caller
    passed straight into ``tools.execute``. Regression guard for "identity
    logic leaked into the loop"."""
    seen: list[ToolContext] = []

    async def whoami(ctx: ToolContext) -> str:
        seen.append(ctx)
        assert ctx.principal is not None
        return ctx.principal.user_id

    reg = ToolRegistry()
    _register(reg, "whoami", whoami, requires_identity=True)

    client = FakeClient(
        [
            _msg(_tool_use("whoami", {}, "toolu_1"), stop_reason="tool_use"),
            _msg(_text("done")),
        ]
    )
    ctx = ToolContext(principal=Principal(user_id="usr_1"))

    result = await _run(
        client, "m", "sys", [{"role": "user", "content": "who am i"}], reg, ctx=ctx
    )

    assert seen == [ctx]
    assert result.tool_calls == [{"tool": "whoami", "args": {}, "output": "usr_1"}]


async def test_identity_gated_tool_without_ctx_is_refused_not_crashed() -> None:
    async def whoami(ctx: ToolContext) -> str:
        return "should not run"

    reg = ToolRegistry()
    _register(reg, "whoami", whoami, requires_identity=True)

    client = FakeClient(
        [
            _msg(_tool_use("whoami", {}, "toolu_1"), stop_reason="tool_use"),
            _msg(_text("done")),
        ]
    )

    result = await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg)

    assert result.tool_calls[0]["output"].startswith(
        "Error: whoami requires an identified user"
    )


async def test_anonymous_turn_never_sees_an_identity_gated_tools_schema() -> None:
    """The model shouldn't waste a round trip discovering a tool it can never
    call — it should never see the tool at all (registry.schemas gating)."""
    reg = ToolRegistry()
    _register(reg, "echo", _echo_fn, requires_identity=False)
    _register(reg, "whoami", _echo_fn, requires_identity=True)

    client = FakeClient([_msg(_text("hi"))])

    await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg)

    sent_names = {t["name"] for t in client.messages.calls[0]["tools"]}
    assert sent_names == {"echo"}


async def test_identified_turn_sees_every_tool_including_gated_ones() -> None:
    reg = ToolRegistry()
    _register(reg, "echo", _echo_fn, requires_identity=False)
    _register(reg, "whoami", _echo_fn, requires_identity=True)

    client = FakeClient([_msg(_text("hi"))])
    ctx = ToolContext(principal=Principal(user_id="usr_1"))

    await _run(client, "m", "sys", [{"role": "user", "content": "hi"}], reg, ctx=ctx)

    sent_names = {t["name"] for t in client.messages.calls[0]["tools"]}
    assert sent_names == {"echo", "whoami"}


async def _echo_fn(**_: object) -> str:
    return "x"


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


def test_redaction_ignores_key_casing_and_separators() -> None:
    """Redaction must not depend on how a schema author capitalized the key: a
    tool declaring `Phone` or `security-code` would otherwise leak into traces
    and the persisted turn tail with no sign anything was missed."""
    redacted = _safe_args(
        {
            "Phone": "+58 412 123 4567",
            "security-code": "123456",
            "API_KEY": "sk-live",
            "Authorization": "Bearer x",
            "orderNumber": "197000001",
            "nested": [{"securityCode": "654321"}],
        }
    )

    assert redacted == {
        "Phone": "[REDACTED]",
        "security-code": "[REDACTED]",
        "API_KEY": "[REDACTED]",
        "Authorization": "[REDACTED]",
        "orderNumber": "197000001",
        "nested": [{"securityCode": "[REDACTED]"}],
    }
