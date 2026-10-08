# Architecture decisions: CollectionsAgent

One row per decision, and every contradiction settled once so it is not settled again, differently, in each file that runs into it.

## Decisions

| Id | Title | Area | Status | Reversibility |
| --- | --- | --- | --- | --- |
| ADR-0001 | Use Python FastAPI with SQLAlchemy and Alembic for the backend | backend | Accepted | awkward: every service module is Python; a rewrite costs the backend |
| ADR-0002 | Use React with Vite served by nginx for the web console | frontend | Accepted | cheap to awkward: screens are components; moving to Next.js reuses them |
| ADR-0003 | Use PostgreSQL 17 with Alembic migrations | database | Accepted | awkward: data and migrations are Postgres-specific (views, SKIP LOCKED) |
| ADR-0004 | Use the MCP Python SDK 2.x with stdio and streamable HTTP | mcp | Accepted | cheap: tools are plain functions behind a registry |
| ADR-0005 | Run the agent as plain orchestrator code over an in-process tool registry | agent orchestration | Accepted | cheap |
| ADR-0006 | Use a Postgres job table with SKIP LOCKED for background work | jobs | Accepted | cheap: jobs are rows; moving to a broker changes the worker only |
| ADR-0007 | Use OpenRouter with a pinned Claude Haiku 4.5 id behind one gateway | llm | Accepted | cheap: model id is configuration |
| ADR-0008 | Use Mailpit as the SMTP test inbox | mail | Accepted | cheap: one image line |
| ADR-0009 | Use seeded users with session cookies and three roles | auth | Accepted | cheap |
| ADR-0010 | Deploy with local Docker Compose only | hosting | Accepted | cheap |
| ADR-0012 | Use the LLM only for prose around placeholders and for reply classification | genai | Accepted | cheap: prompts and the drafting service change; the verifier stays |
| ADR-0011 | Move the payment and clock stories into P0 | scope | Accepted | cheap: a priority change |

## Conflicts that were settled

### Does the mail catcher have to be the MailHog image the brief and REQ-059 name?

- Between: docs/product/brief.md (Phase 10, "mailhog (UI :8025, SMTP :1025)"), REQ-059 ("MailHog test inbox") and ADR-0008 (Mailpit).
- Decision: Mailpit runs under the compose service name `mailhog` on the same ports; docs call it "MailHog-compatible (Mailpit)".
- Why: MailHog is unmaintained since 2020 and 145 MB on a slow link; app code speaks only SMTP.
- Settled by: Savitha Sista (Phase 3 checkpoint, 2026-09-30)
- What now has to change to match: README "real vs simulated" table names Mailpit; REQ-059's wording stays (the brief's term) and its tests target the `mailhog` service.

### Is the web console Next.js, as the brief's default says?

- Between: docs/product/brief.md (Phase 3 default "Next.js/React") and ADR-0002 (React + Vite).
- Decision: React + Vite static build served by nginx.
- Why: no SSR need; avoids a Node image and server runtime on this network.
- Settled by: Savitha Sista (Phase 3 checkpoint, 2026-09-30)
- What now has to change to match: stack rules load `bearing-apps:react`, not `nextjs`; repo-plan lists `web/` under one python-api repository.

### Are the payment and clock stories P1, as the backlog priorities say, or P0?

- Between: docs/product/backlog.md (US-01-004, US-00-017, US-00-019, US-00-020 marked Should) and ADR-0011.
- Decision: built in P0; the backlog Priority cell stays Should so ids and history are unchanged.
- Why: REQ-110 (Must) cannot pass without them.
- Settled by: Savitha Sista (Phase 3 checkpoint, 2026-09-30)
- What now has to change to match: build plan and GSD phase files order them inside P0.

### Is DEMO_TODAY an environment variable or runtime state?

- Between: REQ-022 (`DEMO_TODAY` env, default 2026-09-30) and REQ-023 (admin advances the clock at runtime across api, worker and mcp).
- Decision: `DEMO_TODAY` seeds `settings.demo_today` on migrate and reset; runtime reads the settings row through `clock.today()`.
- Why: an env var cannot change at runtime in three processes.
- Settled by: Savitha Sista (Phase 3 checkpoint, eng review A4)
- What now has to change to match: LLD env table notes `DEMO_TODAY` as the seed value.

### Are the kill switch, autonomy mode, budget and feature flags env vars or runtime state?

- Between: brief section 6 env table (`SENDING_ENABLED`, `AUTONOMY_MODE`, `LLM_BUDGET_USD`, `FEATURE_*`) and REQ-017, REQ-092, AC-US-01-006-1 (admin changes them at runtime and they persist).
- Decision: the env vars seed the `settings` row on migrate and reset; `send_gate`, feature checks and the gateway read the row on every call.
- Why: the same reason as DEMO_TODAY; three processes must agree at once. Raised by the HLD critic (MINOR).
- Settled by: Claude Code under the Phase 3 approval (follows the DEMO_TODAY decision); engineer may reverse
- What now has to change to match: data model adds `settings.feature_*`; LLD env table marks these as seed values.
