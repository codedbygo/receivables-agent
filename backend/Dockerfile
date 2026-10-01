# One image, three commands: api, mcp, worker (eng review A2). Build context: the repo root,
# so prompts/, policy/ and evals/ (replay fixtures) ship with the code that reads them.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /srv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
COPY prompts ./prompts
COPY policy ./policy
COPY evals ./evals
RUN uv sync --locked --no-dev
ENV PATH="/srv/.venv/bin:$PATH"
RUN useradd --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--log-config", "app/core/uvicorn_log.json"]
