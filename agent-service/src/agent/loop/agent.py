"""THE LOOP - observe -> reason -> act repeat. This file is the whole trick.

Every agent framework is ultimately this while-loop with more indirection:

    while not done:
        response = llm(messages, tools)      # resons
        if response asks for tools:
            results = run(tool_calls)        # act
            messages += results              # observe
        else:
            done                             # reply to the human

End-loop guardials (the orange box's exit conditions):
 1. the model stops asking for tools  -> natural end of turn
 2. max_iterations reached            -> hard stop, never spin forever
 3. max_tool_calls reached            -> same hard stop, counted in tool calls
 4. max_turn_tokens reached           -> same hard stop, counted in tokens

Two review hooks sit *around* the act step, not inside the reasoning (ADR-0004):
before a tool batch runs, the decision model may hand the model a second
opinion on a call that doesn't fit the request; before a present_choice pauses
the turn, it may point out the request is answerable without asking. Both are
suggestions delivered once as a tool result — the model stays in charge and
may insist, and the call then runs.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

import anthropic
from anthropic import APIError
from anthropic.types import (
    Message,
    MessageParam,
    TextBlock,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)

# Observers let the gateway show tool calls live and let ops/tracing record
# them - without either being wired into the loop's logic. Defined in
# agent.observability so every layer that emits events shares one signature.
from agent.decide.sites import Decisions, review_batch
from agent.observability import LoopEvent, Observer
from agent.tools.context import ToolContext
from agent.tools.registry import ToolRegistry


@dataclass
class LoopResult:
    reply: str
    tool_calls: list[LoopEvent] = field(default_factory=list)
    iterations: int = 0
    # The turn's text and tool-call groups, in the order they actually
    # happened — e.g. [text, tools, text] for "I'll escalate this" ->
    # escalate_to_human -> "Done, a person will follow up". `reply` alone
    # collapses that back to one string (for callers that just want the
    # final answer); this is what lets a client render the tool activity
    # between the two sentences instead of hoisting it above both.
    segments: list[LoopEvent] = field(default_factory=list)
    needs_human: bool = False
    """Set by ``Agent`` (never by this loop itself) when ``reply`` is a
    harness-level escalation rather than an ordinary answer — e.g. the
    session was already flagged for a human, or a suspended turn ran out of
    iteration budget on resume. Without this, ``ChatResponse``/the SSE
    ``done`` event would carry the exact same machine-readable shape as any
    other reply, leaving a client with no way to tell the two apart short of
    string-matching the text. Not set when the *model* calls
    ``escalate_to_human`` mid-turn and keeps answering — that case already
    shows up in ``segments``/``tool_calls``."""
    message_id: uuid.UUID | None = None
    """The logged assistant message's id — set by ``Agent`` once the turn is
    persisted, so a client can attach feedback to it."""
    suspended: dict[str, Any] | None = None
    """Set when this turn stopped on a suspending tool call (``Tool.suspends``)
    instead of a natural end — everything ``Agent.respond()`` needs to hand to
    ``SessionRepository.set_suspended_tool_use``:
    ``{tool_use_id, tool_name, system, payload, iteration}``. ``turn_tail`` is
    filled in by the caller, which knows where ``session.history`` ends within
    ``messages`` — this loop doesn't."""
    budget_exhausted: str | None = None
    """Which hard budget ended the turn — ``"iterations"``, ``"tool_calls"``
    or ``"tokens"`` — or ``None`` for a natural end."""
    nudges: list[LoopEvent] = field(default_factory=list)
    """Second opinions the decision model handed the model this turn
    (``{site, tool, insisted}``) — how often it spoke up, and whether the
    model agreed or re-issued the call anyway."""
    usage: dict[str, int] = field(default_factory=lambda: {"in": 0, "out": 0})
    """Tokens the turn's LLM calls consumed, summed — what the token budget
    is measured against."""


async def run_loop(
    client: anthropic.AsyncAnthropic,
    model: str,
    system: str,
    messages: list[MessageParam],
    tools: ToolRegistry,
    max_iterations: int = 10,
    max_tokens: int = 2048,
    observer: Observer | None = None,
    stream: bool = False,
    ctx: ToolContext | None = None,
    decisions: Decisions | None = None,
    max_tool_calls: int | None = None,
    max_turn_tokens: int | None = None,
) -> LoopResult:
    """Run one agent turn. `messages` is mutated in place - after the call it
    contains the full working memory of the turn (assistant thoughts, tool
    calls, tool results), which is exactly what gets traced.

    stream=True emits the assistant's text as it's generated (notify("text",
    {"delta": ...})) so a gateway can show it appear token by token - used by
    the web UI. Falls back to a single call for clients without streaming.

    ``ctx`` is forwarded to ``tools.schemas``/``tools.execute`` untouched — the
    loop never reads it. Identity-gating (which tools the model even sees, and
    which calls are allowed to run) lives entirely in ``ToolRegistry``; these
    are the only two lines that touch ``ctx``, so business logic never leaks
    in here.

    ``decisions`` is the harness's decision model (ADR-0004); ``None`` or a
    disabled facade means no review hook runs. ``max_tool_calls`` and
    ``max_turn_tokens`` are the per-turn hard budgets next to
    ``max_iterations`` (CLAUDE.md §2.3); ``None`` means unbounded on that axis.
    """

    notify = observer or (lambda kind, ev: None)
    result = LoopResult(reply="")
    can_stream = stream and hasattr(client.messages, "stream")
    # The registry stays provider-neutral (plain dicts); adapt to the SDK's
    # ToolParam only here, at the Anthropic boundary.
    tool_schemas = cast("list[ToolParam]", tools.schemas(ctx))
    # What the reviewer is told the model can see — the same catalog, as
    # (name, description) pairs; never a tool the model couldn't call.
    visible_tools = [
        (str(schema["name"]), str(schema.get("description", "")))
        for schema in tool_schemas
    ]
    reviewing = decisions is not None and decisions.enabled
    # A suggestion is made at most once per tool per turn (and once per turn
    # for "ask or act"): the second time the model asks, it has already heard
    # the second opinion and insisted — the call runs.
    nudged: set[str] = set()

    def _exhausted(reason: str, **detail: Any) -> LoopResult:
        notify("limit_reached", {"reason": reason, **detail})
        result.budget_exhausted = reason
        result.reply = (
            "(I hit my iteration limit before finishing - "
            "try breaking the request into smaller steps.)"
        )
        result.segments.append({"type": "text", "text": result.reply})
        return result

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration

        # ---- reason: one LLM call with the current working memory ----
        response: Message | None = None
        if can_stream:
            try:
                async with client.messages.stream(
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tool_schemas,
                    max_tokens=max_tokens,
                ) as s:
                    async for delta in s.text_stream:
                        notify("text", {"delta": delta})
                    response = await s.get_final_message()
            except (APIError, ConnectionError) as exc:
                # Surface the hiccup so tracing/ops see it, then fall back to a
                # single call. Auth/rate-limit/validation errors propagate: a
                # retry with the same request would just fail the same way.
                notify("stream_error", {"error": str(exc)})
                response = None
        if response is None:
            response = await client.messages.create(
                model=model,
                system=system,
                messages=messages,
                tools=tool_schemas,
                max_tokens=max_tokens,
            )
        notify(
            "llm",
            {
                "iteration": iteration,
                "stop_reason": response.stop_reason,
                "usage": {
                    "in": response.usage.input_tokens,
                    "out": response.usage.output_tokens,
                },
            },
        )
        result.usage["in"] += response.usage.input_tokens
        result.usage["out"] += response.usage.output_tokens

        # the assistant's turn (text and/or tool requests) joins working memory.
        # Output blocks fed back as input params — cast at the SDK boundary.
        messages.append(
            cast("MessageParam", {"role": "assistant", "content": response.content})
        )

        tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
        text = "".join(b.text for b in response.content if isinstance(b, TextBlock))

        # ---- guardrail 1: no tool calls -> the model is talking to the human
        if not tool_uses:
            if text:
                result.segments.append({"type": "text", "text": text})
            result.reply = "\n\n".join(
                seg["text"] for seg in result.segments if seg["type"] == "text"
            )
            return result

        # A model can talk before it acts ("Voy a escalar esto...") in the same
        # response that asks for a tool — capture that lead-in as its own
        # segment now, before the tool group, so it keeps its place in order.
        if text:
            result.segments.append({"type": "text", "text": text})

        # ---- guardrail 2 (sort of): a suspending tool call pauses the turn.
        # `present_choice` is the first of these — the loop must not call the
        # LLM again this iteration, or the model would have to guess what the
        # customer will answer instead of actually waiting for it.
        suspending = [c for c in tool_uses if tools.suspends(c.name)]

        if suspending and len(tool_uses) > 1:
            # Anthropic requires every tool_use in this message to get a
            # tool_result before the message list is valid again, and a
            # suspending call can't share a batch with others (nothing here
            # could stay "pending" while its batch-mates already got real
            # results) — refuse the whole batch rather than run some tools and
            # strand the rest.
            refusals: list[ToolResultBlockParam] = [
                {
                    "type": "tool_result",
                    "tool_use_id": c.id,
                    "content": (
                        f"Error: {c.name} must be the only tool call in its "
                        "turn when a suspending tool is involved — retry it "
                        "alone."
                    ),
                }
                for c in tool_uses
            ]
            messages.append({"role": "user", "content": refusals})
            result.segments.append(
                {
                    "type": "tools",
                    "calls": [
                        {
                            "tool": c.name,
                            "args": c.input,
                            "output": r["content"],
                            "label": tools.label(
                                c.name, cast("dict[str, Any]", c.input)
                            ),
                        }
                        for c, r in zip(tool_uses, refusals, strict=True)
                    ],
                }
            )
            continue

        if suspending and reviewing and "ask_or_act" not in nudged:
            # ---- review hook 2: ask, or act? One second opinion per turn,
            # before the question pauses everything: if the request looks
            # answerable with the tools at hand, the model hears that as the
            # tool's result and decides. If it asks again, the question shows.
            call = suspending[0]
            args = cast("dict[str, Any]", call.input)
            assert decisions is not None
            verdict = await decisions.ask_or_act(
                cast("list[dict[str, Any]]", messages),
                str(args.get("prompt", "")),
                list(args.get("options", [])),
                visible_tools,
                notify,
            )
            nudged.add("ask_or_act")
            if verdict is not None and verdict.suggestion is not None:
                nudge = {"site": "ask_or_act", "tool": call.name, "insisted": False}
                result.nudges.append(nudge)
                notify("nudge", {**nudge, "suggestion": verdict.suggestion})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call.id,
                                "content": verdict.suggestion,
                            }
                        ],
                    }
                )
                continue
        elif suspending and "ask_or_act" in nudged and result.nudges:
            # The model heard the second opinion and still wants to ask:
            # record that it insisted, and let the question through.
            for nudge in result.nudges:
                if nudge["site"] == "ask_or_act":
                    nudge["insisted"] = True

        if suspending:
            call = suspending[0]  # exactly one — the mixed-batch case above handles >1
            args = cast("dict[str, Any]", call.input)
            notify(
                "tool_start",
                {
                    "tool": call.name,
                    "args": args,
                    "label": tools.label(call.name, args),
                },
            )
            output = await tools.execute(call.name, call.input, ctx)
            event = {"tool": call.name, "args": args, "output": output}
            result.tool_calls.append(event)
            notify("tool", event)
            prompt = args.get("prompt", "")
            options = args.get("options", [])
            notify("choice", {"prompt": prompt, "options": options})
            result.segments.append(
                {"type": "choice", "prompt": prompt, "options": options}
            )
            result.suspended = {
                "tool_use_id": call.id,
                "tool_name": call.name,
                "system": system,
                "payload": args,
                "iteration": iteration,
            }
            # Lead-in text (if any) plus the prompt itself — this is the
            # customer-facing reply for this half of the turn, same idea as
            # the no-tool-calls case joining every text segment.
            texts = [seg["text"] for seg in result.segments if seg["type"] == "text"]
            if prompt:
                texts.append(prompt)
            result.reply = "\n\n".join(texts)
            return result

        # ---- budget: tool calls. Checked before the batch runs, so a turn
        # never executes more calls than it is allowed (CLAUDE.md §2.3).
        if (
            max_tool_calls is not None
            and len(result.tool_calls) + len(tool_uses) > max_tool_calls
        ):
            return _exhausted(
                "tool_calls",
                max_tool_calls=max_tool_calls,
                requested=len(result.tool_calls) + len(tool_uses),
            )

        # ---- review hook 1: a second opinion on each call, once. A call the
        # reviewer confidently flags as a misfit doesn't run this time; the
        # model reads the suggestion as that call's result and decides. The
        # rest of the batch runs as usual. If the model re-issues the flagged
        # call, it runs — the model leads, the reviewer only speaks up.
        refused: dict[str, str] = {}
        if reviewing:
            assert decisions is not None
            reviews = await review_batch(
                decisions,
                cast("list[dict[str, Any]]", messages),
                [(c.name, cast("dict[str, Any]", c.input)) for c in tool_uses],
                visible_tools,
                notify,
            )
            for call, review in zip(tool_uses, reviews, strict=True):
                if review is None or review.suggestion is None:
                    continue
                if call.name in nudged:
                    for nudge in result.nudges:
                        if (
                            nudge["site"] == "tool_review"
                            and nudge["tool"] == call.name
                        ):
                            nudge["insisted"] = True
                    continue
                nudged.add(call.name)
                refused[call.id] = review.suggestion
                nudge = {"site": "tool_review", "tool": call.name, "insisted": False}
                result.nudges.append(nudge)
                notify("nudge", {**nudge, "suggestion": review.suggestion})
        running = [c for c in tool_uses if c.id not in refused]

        # ---- act: execute requested tools concurrently; observe: feed back.
        # Tools are independent (no shared mutable state in the registry), so a
        # batch of N calls takes one round-trip instead of N sequential ones.
        #
        # Announce the batch *before* running it: a tool can take seconds, and
        # the "tool" event below only fires once it has finished. Without this
        # a gateway could not show work in progress, only work already done —
        # and showing a live tool call is exactly what an observer is for.
        for call in running:
            args = cast("dict[str, Any]", call.input)
            notify(
                "tool_start",
                {
                    "tool": call.name,
                    "args": args,
                    # The tool words its own progress line (registry.Tool.label),
                    # so a client renders it without knowing the tool exists.
                    "label": tools.label(call.name, args),
                    # Only present when true, so ordinary events keep their shape.
                    **({"silent": True} if tools.silent(call.name) else {}),
                },
            )
        outputs = await asyncio.gather(
            *(tools.execute(call.name, call.input, ctx) for call in running)
        )
        results_by_id = dict(zip((c.id for c in running), outputs, strict=True))
        tool_results: list[ToolResultBlockParam] = []
        calls: list[LoopEvent] = []
        displays: list[LoopEvent] = []
        for call in tool_uses:
            if call.id in refused:
                # Not executed: the reviewer's suggestion is this call's
                # result. Anthropic still needs a tool_result per tool_use.
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": refused[call.id],
                    }
                )
                continue
            output = results_by_id[call.id]
            args = cast("dict[str, Any]", call.input)
            event = {"tool": call.name, "args": args, "output": output}
            result.tool_calls.append(event)
            done_label = tools.done_label(call.name, args)
            silent = tools.silent(call.name)
            notify(
                "tool",
                {
                    **event,
                    "done_label": done_label,
                    **({"silent": True} if silent else {}),
                },
            )
            if not silent:
                segment_call = {**event, "label": tools.label(call.name, args)}
                if done_label:
                    segment_call["done_label"] = done_label
                calls.append(segment_call)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": output}
            )
            display = tools.display(call.name, output)
            if display is not None:
                displays.append(display)
        if calls:
            result.segments.append({"type": "tools", "calls": calls})
        # What the tools drew for the user goes after their activity group,
        # in call order, and is kept with the message (survives a reload).
        for display in displays:
            notify("display", display)
            result.segments.append(display)

        # Tools that only add to a reply already written (follow-up
        # suggestions) end the turn here: another LLM call would only cost
        # latency. Only when the whole batch is such tools — anything else
        # still needs the model to read its result.
        if running and not refused and all(tools.ends_turn(c.name) for c in running):
            result.reply = "\n\n".join(
                seg["text"] for seg in result.segments if seg["type"] == "text"
            )
            return result
        messages.append({"role": "user", "content": tool_results})

        # ---- budget: tokens. Checked after the batch is observed so the
        # message list is always valid (every tool_use has its tool_result).
        total = result.usage["in"] + result.usage["out"]
        if max_turn_tokens is not None and total >= max_turn_tokens:
            return _exhausted("tokens", max_turn_tokens=max_turn_tokens, used=total)

    return _exhausted("iterations", max_iterations=max_iterations)
