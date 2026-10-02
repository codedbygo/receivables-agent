# Environments

Three environments, promoted in order: local, then dev, then prod. Dev and prod run the same images and the same
two compose files; they differ only in their host and their `.env`. Nothing is promoted until the environment
before it passed its gate.

| | Local | Dev (hosted) | Prod (hosted demo) |
| --- | --- | --- | --- |
| URL | http://localhost:8080 (console), :8025 (Mailpit) | https://`<dev host>` | https://`<prod host>` |
| Deploy | `make web-build up` | `docker compose -f compose.yaml -f compose.prod.yaml up -d --build --wait` on the dev host | the same command on the prod host |
| Env source | `.env` copied from `.env.example` (optional; open roles) | `.env` on the dev host, never in the repo | `.env` on the prod host, never in the repo |
| Sign-in | role picker, no code (`DEMO_OPEN_ROLES=true`) | access code per role | access code per role |
| Reset | `make demo` | `make smoke` (ends at the start of the story) | `make smoke`, or `COMPOSE="..." make demo` |
| Backup | not needed | `make db-backup COMPOSE="docker compose -f compose.yaml -f compose.prod.yaml"` | the same, before every deploy |
| Roll back | `git checkout <previous tag>`, `make up` | previous tag, redeploy, `make db-restore FILE=...` | the same |
| Gate to leave | `make check`, `make coverage`, `make e2e` | `make smoke` passes, `verify-deploy` report | `make smoke` passes, `verify-deploy` report, `/canary` |

## Hosted environment prerequisites (dev and prod)

- A TLS proxy on the host forwarding to `127.0.0.1:8080`. Access codes must never cross plain HTTP. The compose
  files publish nothing on a public interface.
- `.env` on the host with: `POSTGRES_PASSWORD`, `ADMIN_TOKEN`, `COLLECTOR_TOKEN`, `VIEWER_TOKEN`, `MCP_TOKEN`,
  `MAILPIT_UI_AUTH` (`user:password`), `PUBLIC_HOST`, and optionally `OPENROUTER_API_KEY` with `LLM_MODE=live`.
  Compose stops with "set X" when one is missing. Generate codes with `openssl rand -hex 24`.
- `POSTGRES_PASSWORD` takes effect when the data volume is first created. On a host that already ran with the
  default password, change it inside Postgres (`ALTER USER collections PASSWORD ...`) before setting it here.

## Deploy, step by step (the engineer runs these)

1. `make check` and `make coverage` green on the release commit; `make audit` clean.
2. On the host: `make db-backup COMPOSE="docker compose -f compose.yaml -f compose.prod.yaml"`.
3. `git checkout <tag> && make web-build`.
4. `docker compose -f compose.yaml -f compose.prod.yaml up -d --build --wait` (migrations run once in `migrate`).
5. `SMOKE_BASE_URL=http://127.0.0.1:8080 ADMIN_TOKEN=... MCP_TOKEN=... MAILPIT_UI_AUTH=... make smoke`.
6. `verify-deploy` writes `docs/releases/verify-<version>.md`.

Rollback in one sentence: redeploy the previous tag with the same compose command, then
`make db-restore FILE=backups/<pre-deploy backup>.sql` and `make smoke`.

## Fallbacks

- Model unavailable or budget spent: set `LLM_MODE=replay` in the host `.env` and rerun the deploy command.
- Mailpit down: messages show Failed; Resend once it is back (docs/runbooks/demo-day.md).
