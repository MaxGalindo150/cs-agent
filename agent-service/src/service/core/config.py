from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Service root (agent-service/), regardless of the CWD you launch from. This
# microservice owns its own .env locally; in deployed environments the values
# come from the service config / Secret Manager and this file is simply absent
# (real env vars take precedence over the .env file in pydantic-settings).
_service_root = Path(__file__).resolve().parents[3]
_env_file = _service_root / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    # Fail-closed default: a deployment that omits ENVIRONMENT must NOT get dev
    # behavior for free — is_development gates real trust-boundary decisions
    # (the X-User-Id header stub in service/core/identity.py, and /docs
    # exposure in main.py). Local dev sets this explicitly via .env
    # (ENVIRONMENT=dev); so does the test suite (tests/conftest.py).
    environment: str = Field(default="prod", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Apply pending Alembic migrations on startup. Convenient for local dev
    # (bring the service up and the schema is at head). Turn OFF in prod / Cloud
    # Run — migrations belong in the deploy pipeline there, not the request path
    # (see service/core/migrations.py for the why).
    run_migrations_on_startup: bool = Field(
        default=True, alias="RUN_MIGRATIONS_ON_STARTUP"
    )

    api_title: str = "Agent Service API"
    api_version: str = "0.1.0"

    # --- CORS (widget in Webflow calls cross-origin) ---
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        alias="ALLOWED_ORIGINS",
    )

    # --- Anthropic ---
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")

    anthropic_chat_model: str = Field(
        default="claude-sonnet-5",
        alias="ANTHROPIC_CHAT_MODEL",
    )

    anthropic_fast_model: str = Field(
        default="claude-haiku-4-5",
        alias="ANTHROPIC_FAST_MODEL",
    )

    anthropic_chat_fallback_model: str = Field(
        default="claude-sonnet-4-6",
        alias="ANTHROPIC_CHAT_FALLBACK_MODEL",
    )

    # --- Embeddings (semantic memory, ADR-0003) ---
    # Anthropic has no first-party embeddings API and recommends Voyage AI; the
    # agent's semantic-memory store embeds facts/queries via Voyage's REST API
    # (called over httpx, no vendor SDK — see agent/memory/embeddings.py). These
    # values are injected into agent/memory at wiring time; the brain never reads
    # this Settings object (CLAUDE.md §4).
    voyage_api_key: str = Field(alias="VOYAGE_API_KEY")

    embedding_model: str = Field(default="voyage-3.5", alias="EMBEDDING_MODEL")

    embedding_dims: int = Field(default=1024, alias="EMBEDDING_DIMS")

    # --- Tracing ---
    otel_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    trace_dir: Path = Field(default=_service_root / ".traces", alias="TRACE_DIR")

    # --- External systems ---
    # BNPL backend the agent's tools query (see agent/tools/bnpl.py).
    bnpl_api_url: str = Field(default="http://localhost:3001", alias="BNPL_API_URL")

    # --- Database (agent memory & sessions) ---
    # Async SQLAlchemy URL for the `customer_support` Postgres; this service
    # owns the `agent` schema within it. The `+asyncpg` driver is required for
    # the async engine. The default targets the compose Postgres as published
    # on the host (port 5433, so it can coexist with another local Postgres);
    # inside compose the container overrides it with `postgres:5432`, and
    # deployed environments with a real env var / Secret Manager. This value is
    # *injected into* agent/memory at wiring time — the brain never reads this
    # Settings object (see CLAUDE.md §4).
    agent_database_url: str = Field(
        default="postgresql+asyncpg://csa:csa@localhost:5433/customer_support",
        alias="AGENT_DATABASE_URL",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_development(self) -> bool:
        return self.environment == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings (useful in tests)."""
    get_settings.cache_clear()
