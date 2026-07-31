#!/usr/bin/env bash
# Single-entry quality gate for agent-service.
# Same bar as CI — run this before pushing.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ uv lock --check"
uv lock --check

echo "→ uv sync --locked --extra dev"
uv sync --locked --extra dev

echo "→ ruff check"
uv run ruff check src tests

echo "→ ruff format --check"
uv run ruff format --check src tests

echo "→ mypy --strict"
uv run mypy src tests

echo "→ pytest + coverage (≥80% line+branch)"
uv run pytest --cov --cov-report=term-missing --cov-report=xml:coverage.xml -q

echo "✅ All checks passed"
