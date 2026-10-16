"""A scripted ``Decider`` for tests and offline evals.

Lives in the package, not under ``tests/``, on purpose: the deterministic
checks of the harness sites — "given Jev says *this*, does the loop nudge,
does the facade retrieve, does consolidation skip?" — need the same fake as
any integration test that wires a full ``Agent``. One definition, no drift.

Answers are queued in call order. The fake raises if asked something it has
no script for, so a test that forgot to script a site fails loudly instead of
silently taking the fallback path.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from agent.decide.jev import Decision, JevError, Question, State


class FakeDecider:
    def __init__(self) -> None:
        self._scripts: deque[dict[str, Any] | JevError] = deque()
        self.calls: list[tuple[State, dict[str, dict[str, Any]]]] = []

    def script(self, answers: dict[str, Any]) -> FakeDecider:
        """Queue one response: a raw answer dict per question name, built
        with ``noul`` / ``choice`` / ``score`` below. Chainable."""
        self._scripts.append(answers)
        return self

    def fail(self, status: int | None = 503) -> FakeDecider:
        """Queue a failure for the next call."""
        self._scripts.append(
            JevError(
                f"scripted failure (HTTP {status})",
                status=status,
                request_id="req_fake",
            )
        )
        return self

    @property
    def pending(self) -> int:
        return len(self._scripts)

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decision:
        self.calls.append(
            (state, {k: q.model_dump(mode="json") for k, q in questions.items()})
        )
        if not self._scripts:
            raise AssertionError(
                f"FakeDecider has no script for questions {sorted(questions)}"
            )
        nxt = self._scripts.popleft()
        if isinstance(nxt, JevError):
            raise nxt
        missing = set(questions) - set(nxt)
        if missing:
            raise AssertionError(f"script lacks answers for {sorted(missing)}")
        return Decision.model_validate(
            {
                "model": "jev-fake",
                "answers": {k: nxt[k] for k in questions},
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "latency_ms": 1,
            }
        )


def noul(p: float) -> dict[str, Any]:
    return {"type": "noul", "noul": p}


def choice(label: str, confidence: float, **others: float) -> dict[str, Any]:
    probs = {label: confidence, **others}
    return {
        "type": "choice",
        "choice": label,
        "probabilities": probs,
        "confidence": confidence,
    }


def score(
    level: float,
    confidence: float,
    levels: int = 3,
    probabilities: dict[str, float] | None = None,
) -> dict[str, Any]:
    """A score answer. By default all of ``confidence`` sits on ``level``;
    pass ``probabilities`` to shape the distribution (a split between two
    adjacent levels, a bimodal one) the way the live model returns it."""
    if probabilities is None:
        probabilities = {str(i): 0.0 for i in range(levels)}
        probabilities[str(int(level))] = confidence
    return {
        "type": "score",
        "score": level,
        "legend": {str(i): f"level {i}" for i in range(levels)},
        "probabilities": probabilities,
        "confidence": confidence,
    }
