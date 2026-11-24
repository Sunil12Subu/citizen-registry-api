# ---------- Stage 1: build the environment ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Compile .py to bytecode for faster startup; copy files instead of linking;
# use the image's Python instead of downloading another one.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# 1) Install ONLY the libraries first. This layer is cached and reused
#    until pyproject.toml or uv.lock changes, so code edits rebuild in seconds.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# 2) Then install our own code (non-editable: copied into .venv, not linked to src/)
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------- Stage 2: the small runtime image ----------
FROM python:3.12-slim

# Run as a normal user, not root: if the app is ever compromised, the attacker has less power
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000

CMD ["uvicorn", "citizen_registry_api.main:app", "--host", "0.0.0.0", "--port", "8000"]