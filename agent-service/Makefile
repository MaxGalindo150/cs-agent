# agent-service — one command per job.
#
# Make ships with every Mac/Linux box; each target below is just the shell
# command you'd otherwise have to remember and retype. `make test` runs the
# pytest line below, nothing more — no framework where a shortcut will do
# (CLAUDE.md §3: "no orchestration framework", same spirit here).
#
# `make` alone (or `make help`) lists every target with its one-line purpose.

.DEFAULT_GOAL := help
.PHONY: help install dev lint format format-check types test test-cov \
        check eval eval-judge migrate migrate-down migrate-new clean

## ── Setup ────────────────────────────────────────────────────────────────

install: ## Install dependencies, including dev tools (ruff, mypy, pytest, deepeval)
	uv sync --extra dev

## ── Run ──────────────────────────────────────────────────────────────────

dev: ## Run the API locally with autoreload
	uv run uvicorn service.main:app --reload

## ── Quality gates (CLAUDE.md §6/§7) ─────────────────────────────────────

lint: ## Lint (ruff check)
	uv run ruff check src tests evals

format: ## Auto-format in place (ruff format)
	uv run ruff format src tests evals

format-check: ## Check formatting without changing files (CI mode)
	uv run ruff format --check src tests evals

types: ## Type-check (mypy --strict)
	uv run mypy src tests

test: ## Deterministic test suite — Level 1, no network, <30s (CLAUDE.md §8)
	uv run pytest

test-cov: ## Tests with a coverage report (fail_under = 80%, see pyproject.toml)
	uv run pytest --cov=agent --cov=service --cov-report=term-missing

check: lint format-check types test ## Everything CI runs — the pre-push gate
	@echo "✓ all checks passed"

## ── Evals — Level 2, against the real LLM (CLAUDE.md §8) ───────────────

eval: ## Deterministic tool-selection eval (real LLM, code-checked pass/fail)
	uv run pytest evals/deterministic -v

eval-judge: ## LLM-as-judge eval (scored %, needs a real ANTHROPIC_API_KEY)
	uv run pytest evals/judge -v

## ── Database (alembic) ──────────────────────────────────────────────────

migrate: ## Apply pending migrations
	uv run alembic upgrade head

migrate-down: ## Roll back the last migration
	uv run alembic downgrade -1

migrate-new: ## Create a new migration: make migrate-new MSG="add x column"
	uv run alembic revision --autogenerate -m "$(MSG)"

## ── Housekeeping ─────────────────────────────────────────────────────────

clean: ## Remove caches and coverage artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
