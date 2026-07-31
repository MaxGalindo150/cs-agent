"""HERO MOMENT #1 — the gate that decides WHETHER to retrieve memory at all.

The top audience question across platforms: "why hit the memory store every
turn?" Default-on retrieval is (a) slow — an extra search before every reply —
and (b) worse: irrelevant memories bias the answer ("over-interpretation").

So before touching any store, a cheap fast model answers one question:
    does THIS message need the user's memory?
"what's 2+2" → no. "when am I meeting Alex?" → yes, and here's the search query.

Cost: one small-model call (~a few hundred tokens). Payoff: retrieval only
when it helps. This is the same judge pattern as LLM-as-judge in evals —
a small model making one narrow decision.
"""

from __future__ import annotations

import json

import anthropic

GATE_PROMPT = """\
You are a retrieval gate for a customer support assistant's memory of THIS customer.
Memory holds: the customer's profile and entitlements (plan, product config,
integrations, preferences) and summaries of their PAST TICKETS (what they
reported, and how each was resolved).

Given the customer's incoming message, decide whether answering well requires
that stored history.

Reply with ONLY this JSON, nothing else:
{{"retrieve": true/false, "query": "<keywords or empty>", "reason": "<5 words>"}}

Retrieve (true) when the message:
- refers to a prior contact: "again", "still", "last time", "same issue"
- reports a problem whose cause could depend on their setup, plan, or a past fix
- asks about their account, billing, limits, entitlements, or an open request
- is a follow-up, escalation, or complaint about how something was handled

Do NOT retrieve (false) when the message is:
- a greeting, thanks, or closing pleasantry
- general product how-to answerable from documentation alone
- fully self-contained: every detail needed to answer is in the message itself

When unsure, retrieve: a missed piece of the customer's history is worse than
one extra lookup.

"query" must be keywords for a full-text search over past tickets — use the
product area, feature, and error terms, not a restatement of the whole message.

Customer message: {message}"""


async def should_retrieve(
    client: anthropic.AsyncAnthropic, small_model: str, message: str
) -> tuple[bool, str, str]:
    """Returns (retrieve?, search_query, reason). Fails open: if the gate
    itself errors, we retrieve — a stale memory beats a lost one."""
    try:
        response = await client.messages.create(
            model=small_model,
            # generous budget: reasoning models (Kimi K3, ...) spend a thinking
            # block BEFORE the JSON — 100 tokens was truncating the answer away
            max_tokens=600,
            messages=[{"role": "user", "content": GATE_PROMPT.format(message=message)}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        if "{" not in text:  # a reasoning-only / truncated reply, not an error
            return True, message, "gate returned no JSON — failing open"
        decision = json.loads(text[text.index("{") : text.rindex("}") + 1])
        return (
            bool(decision.get("retrieve")),
            decision.get("query", message),
            decision.get("reason", ""),
        )
    except Exception as exc:
        return True, message, f"gate failed open ({type(exc).__name__})"
