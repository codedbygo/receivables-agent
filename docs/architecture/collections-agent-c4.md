# C4: AI Receivables Collections Agent

Sources: docs/design/collections-hld.md, docs/architecture/architecture.json, api/openapi.yaml, ADR-0001 to ADR-0010. No code exists yet; every box is from the design, not the repository.

Drawn views: `docs/architecture/diagrams/CollectionsAgent_SystemArchitecture_v1.svg`, `_ArchitectureFlow_v1.svg`, `_DeploymentArchitecture_v1.svg` (render.py, diagram-check 0 problems).

## Context

```mermaid
C4Context
  title Collections Agent: system context
  Person(collector, "Collector", "Approves drafts, handles escalations")
  Person(admin, "Admin", "Runs the demo, controls sending and cost")
  Person_Ext(customer, "Customer", "B2B buyer who owes money and replies")
  System(ca, "Collections Agent", "Prioritises, drafts, verifies, sends, understands replies, reconciles")
  System_Ext(or, "OpenRouter", "Claude Haiku 4.5")
  System_Ext(mail, "Mailpit", "SMTP test inbox")
  System_Ext(bank, "Bank feed (simulated)", "Signed credits")
  System_Ext(cc, "Claude Code", "External MCP client")
  Rel(collector, ca, "Uses", "browser")
  Rel(admin, ca, "Administers", "browser")
  Rel(ca, or, "Prose and classification", "HTTPS")
  Rel(ca, mail, "Approved reminders", "SMTP")
  Rel(mail, customer, "stands in for the customer's inbox")
  Rel(customer, ca, "Replies (entered via Simulate reply)")
  Rel(bank, ca, "Credits", "HMAC webhook")
  Rel(cc, ca, "Tools", "MCP stdio")
```

## Containers

```mermaid
C4Container
  title Collections Agent: containers (Docker Compose)
  Person(collector, "Collector")
  Container(web, "web", "nginx + React build", "Console")
  Container(api, "api", "FastAPI", "REST, webhook, sessions, admin")
  Container(mcp, "mcp", "mcp 2.x", "Tools over stdio and HTTP")
  Container(worker, "worker", "Python", "Daily run, promise check, sends")
  ContainerDb(db, "postgres", "PostgreSQL 17", "Ledger, audit, jobs")
  System_Ext(mail, "mailhog", "Mailpit")
  System_Ext(or, "OpenRouter")
  Rel(collector, web, "HTTP 8080")
  Rel(web, api, "/api/v1")
  Rel(api, db, "SQL")
  Rel(mcp, db, "SQL via services")
  Rel(worker, db, "SQL, SKIP LOCKED")
  Rel(worker, mail, "SMTP 1025")
  Rel(worker, or, "HTTPS")
  Rel(api, or, "HTTPS (replies)")
```

## Components (backend)

Orchestrator (4 roles, 4-call bound) → tool registry → services (ledger, drafting, guardrails, approval and send gate, payments, promises, disputes, escalations, timeline) → PostgreSQL; orchestrator → gateway → OpenRouter. See the system diagram's Core group.

## Sequences

The three flows (daily run to send, reply to promise or dispute, bank feed to promise fulfilled) are in HLD section 2.
