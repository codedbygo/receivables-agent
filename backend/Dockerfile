# One image, three commands: api, mcp, worker (eng review A2). Build context: the repo root,
# so prompts/, policy/ and evals/ (replay fixtures) ship with the code that reads them.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /srv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --extra voice --no-install-project
COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
COPY prompts ./prompts
COPY policy ./policy
COPY evals ./evals
RUN uv sync --locked --no-dev --extra voice
ENV PATH="/srv/.venv/bin:$PATH"
RUN useradd --uid 10001 app
# Web calls (ADR-0019): the Whisper model ships in the image, so a call never waits on a download. Another size
# (WHISPER_MODEL=small) downloads once on first use into the same app-owned cache.
ENV HF_HOME=/srv/models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')" \
    && chown -R app /srv/models
USER app
EXPOSE 8000
CMD ["uvicorn", "app.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--log-config", "app/core/uvicorn_log.json"]
