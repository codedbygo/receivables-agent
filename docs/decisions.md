# Decision log

One row per technology decision. The ADR holds the full reasoning; this table is the index. `tech-decision` maintains it.

| Date | Key | Choice | Recommended | Why it was chosen | ADR | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-30 | backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, uv | same | the brief names it, the MCP spike proved it here, and one language keeps the service layer single (eng review A1, A2) | ADR-0001 | Accepted |
| 2026-09-30 | frontend | React 19 + Vite + TanStack Query + Tailwind, static build served by nginx | same | it needs no server runtime, avoids a Node image on this network, and matches Bearing's react house rules (eng review A8) | ADR-0002 | Accepted |
| 2026-09-30 | database | PostgreSQL 17 (postgres:17-alpine) | same | the brief fixes Postgres and 17 is current and already on the machine | ADR-0003 | Accepted |
| 2026-09-30 | mcp | mcp>=2.2,<3 with MCPServer | same | the spike proved it here | ADR-0004 | Accepted |
| 2026-09-30 | agent orchestration | Plain orchestrator calling the shared tool registry in-process | same | it removes a network hop and keeps tests fast (eng review A3) | ADR-0005 | Accepted |
| 2026-09-30 | jobs | Postgres jobs table, SELECT FOR UPDATE SKIP LOCKED, unique (kind, run_date) | same | it needs no new service and makes idempotency a database constraint (eng review A5) | ADR-0006 | Accepted |
| 2026-09-30 | llm | anthropic/claude-haiku-4.5, pinned | same | pinning keeps replay keys and eval numbers stable | ADR-0007 | Accepted |
| 2026-09-30 | mail | Mailpit, compose service still named mailhog | same | it is maintained, small and already cached; application code only speaks SMTP | ADR-0008 | Accepted |
| 2026-09-30 | auth | Seeded users, server session cookie, ADMIN_TOKEN for scripts | same | it gives the role matrix with no external provider | ADR-0009 | Accepted |
| 2026-09-30 | hosting | Local Docker Compose | same | We will ship local Docker Compose with six services (postgres, mailhog, api, mcp, worker, web); a hosted demo is a separate later decision | ADR-0010 | Accepted |
| 2026-09-30 | scope | Move the four stories (11 points) into P0 | same | the brief marks the whole story as must be flawless | ADR-0011 | Accepted |
| 2026-09-30 | genai | LLM for prose around placeholders and reply classification only | same | non-negotiable 2: code owns every value | ADR-0012 | Accepted |
| 2026-10-08 | auth | Google sign-in and email with password, per-person users, signed cookie session | Google sign-in only | the engineer wants people without a Google account to sign in too; both replace the shared role codes so audit names a person | ADR-0019 | Accepted |
