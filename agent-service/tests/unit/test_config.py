"""Bounds on the consolidation settings — a misconfigured deployment must
fail fast at settings load, not hang or crash mid-sweep (agent/memory/
consolidation.py, service/worker/consolidate.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from service.core.config import Settings


@pytest.mark.parametrize("value", [0, -1])
def test_consolidate_every_rejects_non_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(CONSOLIDATE_EVERY=value)


@pytest.mark.parametrize("value", [0, -1])
def test_consolidate_batch_size_rejects_non_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(CONSOLIDATE_BATCH_SIZE=value)


@pytest.mark.parametrize("value", [0, -1])
def test_consolidate_concurrency_rejects_non_positive(value: int) -> None:
    """0 would make asyncio.Semaphore(0) never releasable, hanging every
    sweep forever — this must be caught at settings load, not at request
    time."""
    with pytest.raises(ValidationError):
        Settings(CONSOLIDATE_CONCURRENCY=value)


@pytest.mark.parametrize("value", [0.49, 1.01])
def test_jev_confidence_threshold_is_bounded(value: float) -> None:
    """Below 0.5 a 'confident' choice could be the minority label; above 1
    nothing would ever be confident — both are configuration mistakes."""
    with pytest.raises(ValidationError):
        Settings(JEV_CONFIDENCE_THRESHOLD=value)


def test_turn_budgets_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(MAX_TOOL_CALLS_PER_TURN=0)
    with pytest.raises(ValidationError):
        Settings(MAX_TOKENS_PER_TURN=0)


def test_decider_is_off_without_a_key() -> None:
    from service.core.agent import build_decider

    assert build_decider(Settings(TYPESAFE_API_KEY="")) is None
