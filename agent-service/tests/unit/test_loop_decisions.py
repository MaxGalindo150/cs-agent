"""Unit tests for the loop's review hooks and hard budgets (Level 1 — fake LLM,
FakeDecider).

The contract under test: a reviewer's suggestion is delivered once as a tool
result and the model stays in charge (a re-issued call runs); an "act"
verdict holds a present_choice back once; the tool-call and token budgets
end the turn with the same limit reply and a traced reason.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Literal, cast

import anthropic
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from agent.decide.fake import FakeDecider, choice, noul, score
from agent.decide.sites import Decisions
from agent.loop.agent import LoopResult, run_loop
from agent.tools.implementations.present_choice import make_present_choice_tool
from agent.tools.registry import Tool, ToolRegistry

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _tool_use(name: str, args: dict[str, Any], block_id: str) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=block_id, name=name, input=args)


def _msg(
    *blocks: Any,
    stop_reason: Literal["end_turn", "tool_use"] = "end_turn",
    tokens: tuple[int, int] = (1, 1),
) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=list(blocks),
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=tokens[0], output_tokens=tokens[1]),
    )


class _FakeMessages:
    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[Message]) -> None:
        self.messages = _FakeMessages(responses)


def _registry(*names: str) -> tuple[ToolRegistry, list[str]]:
    ran: list[str] = []
    reg = ToolRegistry()
    for name in names:

        async def fn(_name: str = name, **kw: Any) -> str:
            ran.append(_name)
            return f"{_name} ok"

        reg.register(
            Tool(name=name, description=f"{name} desc", input_schema=_SCHEMA, fn=fn)
        )
    return reg, ran


def _run(
    client: object,
    messages: list[Any],
    tools: ToolRegistry,
    **kw: Any,
) -> Awaitable[LoopResult]:
    return run_loop(
        cast(anthropic.AsyncAnthropic, client), "m", "sys", messages, tools, **kw
    )


def _fit(tool: str) -> dict[str, Any]:
    return {"fits": noul(0.95), "best_tool": choice(tool, 1.0), "risk": score(0, 1)}


def _misfit(better: str) -> dict[str, Any]:
    return {"fits": noul(0.1), "best_tool": choice(better, 0.95), "risk": score(0, 1)}


# ---- tool review ----------------------------------------------------------------


async def test_confident_misfit_is_refused_once_then_runs_when_reissued() -> None:
    tools, ran = _registry("search_orders", "get_order_detail")
    fake = (
        FakeDecider()
        .script(_misfit("get_order_detail"))
        .script(_misfit("get_order_detail"))
    )
    client = FakeClient(
        [
            _msg(_tool_use("search_orders", {}, "t1"), stop_reason="tool_use"),
            _msg(_tool_use("search_orders", {}, "t2"), stop_reason="tool_use"),
            _msg(_text("listo")),
        ]
    )
    events: list[tuple[str, dict[str, Any]]] = []
    messages: list[Any] = [{"role": "user", "content": "detalle de la 924141"}]

    result = await _run(
        client,
        messages,
        tools,
        observer=lambda k, e: events.append((k, e)),
        decisions=Decisions(fake),
    )

    # first call did not run; its tool_result is the suggestion
    assert ran == ["search_orders"]
    first_result = client.messages.calls[1]["messages"][-1]["content"][0]
    assert first_result["tool_use_id"] == "t1"
    assert "Harness review" in first_result["content"]
    assert "get_order_detail" in first_result["content"]
    # the model insisted: recorded, and the second call ran
    assert result.nudges == [
        {"site": "tool_review", "tool": "search_orders", "insisted": True}
    ]
    assert [k for k, _ in events if k == "nudge"] == ["nudge"]
    assert [e["site"] for k, e in events if k == "decision"] == [
        "tool_review",
        "tool_review",
    ]
    assert result.reply == "listo"
    assert result.iterations == 3


async def test_fit_calls_run_and_mixed_batches_only_hold_the_misfit() -> None:
    tools, ran = _registry("a", "b")
    fake = FakeDecider().script(_fit("a")).script(_misfit("a"))
    client = FakeClient(
        [
            _msg(
                _tool_use("a", {}, "t1"),
                _tool_use("b", {}, "t2"),
                stop_reason="tool_use",
            ),
            _msg(_text("ok")),
        ]
    )
    messages: list[Any] = [{"role": "user", "content": "x"}]

    result = await _run(client, messages, tools, decisions=Decisions(fake))

    assert ran == ["a"]
    tool_results = client.messages.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in tool_results] == ["t1", "t2"]
    assert tool_results[0]["content"] == "a ok"
    assert "Harness review" in tool_results[1]["content"]
    assert len(result.tool_calls) == 1
    assert result.nudges == [{"site": "tool_review", "tool": "b", "insisted": False}]


async def test_reviewer_failure_lets_every_call_run() -> None:
    tools, ran = _registry("a")
    fake = FakeDecider().fail(503)
    client = FakeClient(
        [_msg(_tool_use("a", {}, "t1"), stop_reason="tool_use"), _msg(_text("ok"))]
    )
    result = await _run(
        client, [{"role": "user", "content": "x"}], tools, decisions=Decisions(fake)
    )
    assert ran == ["a"] and result.nudges == []


async def test_disabled_decisions_make_no_calls() -> None:
    tools, ran = _registry("a")
    fake = FakeDecider()  # any call would raise: nothing scripted
    client = FakeClient(
        [_msg(_tool_use("a", {}, "t1"), stop_reason="tool_use"), _msg(_text("ok"))]
    )
    await _run(
        client, [{"role": "user", "content": "x"}], tools, decisions=Decisions(None)
    )
    assert ran == ["a"] and fake.calls == []


# ---- ask or act ---------------------------------------------------------------


async def test_act_verdict_holds_the_question_back_once() -> None:
    tools, ran = _registry("get_order_detail")
    tools.register(make_present_choice_tool())
    options = [{"id": "a", "label": "la 1"}, {"id": "b", "label": "la 2"}]
    fake = (
        FakeDecider()
        .script({"action": choice("act", 0.9)})
        .script(_fit("get_order_detail"))
    )
    client = FakeClient(
        [
            _msg(
                _tool_use(
                    "present_choice", {"prompt": "¿cuál?", "options": options}, "c1"
                ),
                stop_reason="tool_use",
            ),
            _msg(_tool_use("get_order_detail", {}, "t1"), stop_reason="tool_use"),
            _msg(_text("la 924141 está en progreso")),
        ]
    )
    messages: list[Any] = [{"role": "user", "content": "detalle de la 924141"}]

    result = await _run(client, messages, tools, decisions=Decisions(fake))

    assert result.suspended is None
    assert ran == ["get_order_detail"]
    held = client.messages.calls[1]["messages"][-1]["content"][0]
    assert held["tool_use_id"] == "c1" and "present_choice" in held["content"]
    assert result.nudges == [
        {"site": "ask_or_act", "tool": "present_choice", "insisted": False}
    ]


async def test_model_may_insist_on_asking_and_the_question_then_shows() -> None:
    tools, _ = _registry("get_order_detail")
    tools.register(make_present_choice_tool())
    options = [{"id": "a", "label": "la 1"}, {"id": "b", "label": "la 2"}]
    ask = _tool_use("present_choice", {"prompt": "¿cuál?", "options": options}, "c1")
    ask_again = _tool_use(
        "present_choice", {"prompt": "¿cuál?", "options": options}, "c2"
    )
    fake = FakeDecider().script({"action": choice("act", 0.9)})
    client = FakeClient(
        [_msg(ask, stop_reason="tool_use"), _msg(ask_again, stop_reason="tool_use")]
    )

    result = await _run(
        client, [{"role": "user", "content": "x"}], tools, decisions=Decisions(fake)
    )

    assert result.suspended is not None and result.suspended["tool_use_id"] == "c2"
    assert result.nudges == [
        {"site": "ask_or_act", "tool": "present_choice", "insisted": True}
    ]
    assert fake.calls and len(fake.calls) == 1  # asked the reviewer once


async def test_ask_verdict_lets_the_question_through_untouched() -> None:
    tools, _ = _registry()
    tools.register(make_present_choice_tool())
    options = [{"id": "a", "label": "x"}, {"id": "b", "label": "y"}]
    fake = FakeDecider().script({"action": choice("ask", 0.9)})
    client = FakeClient(
        [
            _msg(
                _tool_use("present_choice", {"prompt": "?", "options": options}, "c1"),
                stop_reason="tool_use",
            )
        ]
    )
    result = await _run(
        client, [{"role": "user", "content": "x"}], tools, decisions=Decisions(fake)
    )
    assert result.suspended is not None and result.nudges == []


# ---- budgets ------------------------------------------------------------------


async def test_tool_call_budget_ends_the_turn_before_the_batch_runs() -> None:
    tools, ran = _registry("a")
    client = FakeClient(
        [
            _msg(_tool_use("a", {}, "t1"), stop_reason="tool_use"),
            _msg(
                _tool_use("a", {}, "t2"),
                _tool_use("a", {}, "t3"),
                stop_reason="tool_use",
            ),
        ]
    )
    events: list[tuple[str, dict[str, Any]]] = []

    result = await _run(
        client,
        [{"role": "user", "content": "x"}],
        tools,
        observer=lambda k, e: events.append((k, e)),
        max_tool_calls=2,
    )

    assert ran == ["a"]  # the 2-call batch would exceed 2 → never ran
    assert result.budget_exhausted == "tool_calls"
    assert "iteration limit" in result.reply
    limit = [e for k, e in events if k == "limit_reached"]
    assert limit == [{"reason": "tool_calls", "max_tool_calls": 2, "requested": 3}]


async def test_token_budget_ends_the_turn_after_the_batch_is_observed() -> None:
    tools, ran = _registry("a")
    client = FakeClient(
        [
            _msg(_tool_use("a", {}, "t1"), stop_reason="tool_use", tokens=(900, 200)),
            _msg(_text("never reached")),
        ]
    )
    messages: list[Any] = [{"role": "user", "content": "x"}]

    result = await _run(client, messages, tools, max_turn_tokens=1000)

    assert ran == ["a"]
    assert result.budget_exhausted == "tokens"
    assert result.usage == {"in": 900, "out": 200}
    # the message list is still valid: the tool_use got its tool_result
    assert messages[-1]["content"][0]["type"] == "tool_result"


async def test_iteration_limit_is_traced_with_its_reason() -> None:
    tools, _ = _registry("a")
    client = FakeClient(
        [_msg(_tool_use("a", {}, f"t{i}"), stop_reason="tool_use") for i in range(3)]
    )
    events: list[tuple[str, dict[str, Any]]] = []
    result = await _run(
        client,
        [{"role": "user", "content": "x"}],
        tools,
        observer=lambda k, e: events.append((k, e)),
        max_iterations=3,
    )
    assert result.budget_exhausted == "iterations"
    assert [e for k, e in events if k == "limit_reached"] == [
        {"reason": "iterations", "max_iterations": 3}
    ]


async def test_natural_end_has_no_budget_reason_and_sums_usage() -> None:
    tools, _ = _registry("a")
    client = FakeClient(
        [
            _msg(_tool_use("a", {}, "t1"), stop_reason="tool_use", tokens=(10, 5)),
            _msg(_text("ok"), tokens=(20, 7)),
        ]
    )
    result = await _run(client, [{"role": "user", "content": "x"}], tools)
    assert result.budget_exhausted is None
    assert result.usage == {"in": 30, "out": 12}
