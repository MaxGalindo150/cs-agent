# Dev image for agent-service (FastAPI + uv).
#
# Bakes in dependencies only; source is bind-mounted at runtime (see
# ../docker-compose.yml) so `uvicorn --reload` picks up code changes without
# a rebuild. Rebuild only when pyproject.toml/uv.lock change.
#
# NOTE: this is a dev image (hot-reload, dev extras installed). A separate
# production Dockerfile (multi-stage, slim, non-root) is still planned per
# agent-service/CLAUDE.md and is out of scope here.
FROM python:3.13-slim

# uv: the package manager this service standardizes on.
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY . .
RUN uv sync --frozen --extra dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "service.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
