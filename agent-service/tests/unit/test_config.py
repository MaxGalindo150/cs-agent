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
