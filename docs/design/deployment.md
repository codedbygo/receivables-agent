# Deployment architecture: AI Receivables Collections Agent

Diagram: docs/architecture/diagrams/CollectionsAgent_DeploymentArchitecture_v1.svg. Decision: ADR-0010 (local Docker Compose only).

| Environment | Where | Purpose | Data |
| --- | --- | --- | --- |
| local | engineer laptop, `docker compose up` | development, rehearsal, the live demo | seeded, reset with `make reset-demo` |
| ci | GitHub Actions runner | `make check` with Postgres as a service container, no network to OpenRouter | created per job |
| hosted demo | not built (optional, separate decision) | n/a | n/a |

Topology (compose, one network): `postgres` (postgres:17-alpine, named volume, healthcheck `pg_isready`, host port 127.0.0.1:${POSTGRES_PORT:-5433}), `mailhog` (Mailpit; SMTP 1025 on the network, UI bound to 127.0.0.1:8025), `api` (backend image, `uvicorn`, 127.0.0.1:8000), `mcp` (backend image, streamable HTTP on 127.0.0.1:8001; stdio via `docker compose exec -T mcp python -m app.mcp --stdio`), `worker` (backend image, `python -m app.worker`), `web` (nginx:stable-alpine serving `web/dist`, proxying `/api` to `api`, 127.0.0.1:8080). Start order by healthchecks: postgres, then migrate (one-shot), then api, mcp, worker, web.

Secrets: `.env` beside compose (never committed); `.env.example` lists every variable. `OPENROUTER_API_KEY` is only read when `LLM_MODE` is `live` or `record`.

Scaling: one of each; no replicas (HLD section 8).

Backups and DR: none; demo data is reproducible from the seed. The `llm_calls` table (spend) survives reset but not `docker compose down -v`.

Rollback: check out the previous commit, `make migrate-down` to its revision, `docker compose build`, `make reset-demo`. Images are local, so there is no registry tag to roll back to.

Before demo day (slow network): run `docker compose pull` and `docker compose build` the day before; set `LLM_MODE=replay` by default (runbook `docs/runbooks/demo-day.md`, Phase 10).
