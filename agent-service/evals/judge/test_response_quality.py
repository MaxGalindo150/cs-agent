"""LLM-AS-JUDGE EVAL — "did the agent avoid promising something it can't
back?" This is NOT a unit test: a judge model scores something no plain
assert can check — whether the reply's wording invents a specific outcome,
amount, or timeline. Scores are a 0-1 percentage against a threshold, never
confused with the deterministic pass/fail next door
(``evals/deterministic/test_tool_trigger.py``).

This is the direct regression eval for the bug that started this: the agent
said "voy a escalar esto para que te reembolsen" — offering a concrete
outcome it had no tool to back. ``escalate_to_human`` firing (checked
deterministically) is necessary but not sufficient — the WORDING of the
reply around that call is what this checks.

Requires a real ANTHROPIC_API_KEY: the judge is a real model call, same as
the turn itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from agent.memory.db import Database
from evals.helpers import HAS_KEY, make_agent_live

if TYPE_CHECKING:
    from deepeval.metrics import GEval

pytestmark = pytest.mark.skipif(
    not HAS_KEY, reason="LLM-as-judge needs a real ANTHROPIC_API_KEY"
)


@pytest.fixture(scope="module")
def no_unbacked_promises_metric() -> GEval:
    # Imported lazily (not at module level) so collecting this file — even
    # when the skip above fires — never pays deepeval's import cost, same as
    # Waku's judge tests do.
    from deepeval.metrics import GEval
    from deepeval.test_case import SingleTurnParams

    from evals.judge.anthropic_judge import AnthropicJudge

    judge = AnthropicJudge()
    return GEval(
        name="NoUnbackedPromises",
        criteria=(
            "The assistant reply must NOT promise a specific outcome, amount, "
            "or timeline for something it cannot verify or resolve itself (a "
            "refund, a manual account change, anything outside its own tools). "
            "If it can't help directly, it should say so plainly and hand off "
            "to a human, never invent a result it has no way to guarantee."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=judge,
        threshold=0.7,
    )


async def test_an_uncovered_request_does_not_promise_an_outcome(
    database: Database, no_unbacked_promises_metric: GEval
) -> None:
    from deepeval import assert_test  # type: ignore[attr-defined]
    from deepeval.test_case import LLMTestCase

    agent = make_agent_live(database)
    user_message = "Hola, quiero cambiar mi email a otro correo"
    session_id = await agent.start_session("eval")

    result = await agent.respond(session_id, user_message)

    assert_test(
        LLMTestCase(input=user_message, actual_output=result.reply),
        [no_unbacked_promises_metric],
    )
