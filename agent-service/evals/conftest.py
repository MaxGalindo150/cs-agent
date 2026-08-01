"""Path shim so ``evals`` is importable when running ``pytest evals`` from the
service root (mirrors Waku's ``evals/conftest.py``, which does the identical
shim for ``waku/`` vs. ``evals/``).

The ``database`` fixture (a real, migrated Postgres, truncated between tests)
is NOT redefined here — it's the exact same real-Postgres harness
``tests/integration/`` already has, so this re-exports it rather than
maintaining a second copy of migration/truncation logic that would drift.
Evals run against the dedicated TEST database (``customer_support_test``),
never the dev one the running app talks to — a turn's session/messages get
truncated away after each eval, same as any integration test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.integration.conftest import (  # noqa: E402,F401
    database,
    migrated_database_url,
)
