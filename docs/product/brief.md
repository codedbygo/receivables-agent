# Brief: AI Receivables Collections Agent (hackathon master prompt)

Source: the master prompt pasted into the Claude Code session on 2026-09-30 by the engineer. Kept here verbatim for the product sections (4 to 8), except that em dashes are replaced by separators so every REQ can cite a line; the process sections (0 to 3) are summarised in `docs/process/bearing-notes.md`.

## 0. Mission and non-negotiables

Mission: Build an AI Receivables Collections Agent for Indian B2B companies ("an AI employee that manages unpaid invoices") whose behaviour can be demonstrated, measured, audited and trusted.

1. Bearing is the spine.
2. The ledger is the source of truth. The LLM never computes, invents, rounds or totals money. All money is stored as integer paise (`BIGINT`), formatted as INR (`₹7,50,000`) only at the edge.
3. Every outbound message passes deterministic guardrails and human approval (except the explicitly allow-listed Trusted-mode case).
4. The agent loop is bounded (max 4 tool calls per customer per run) and fully logged.
5. No live dependency in tests. CI passes with no OpenRouter key, no network, no real mail/WhatsApp/bank.
6. Bearing's guard rules stand. Never git push, merge, tag, deploy, docker push or run infra-changing commands. Print the command; the engineer runs it.
7. Traceability. Every artifact carries the IDs it derives from (REQ-nnn to US-nnn/AC-nnn to TC-nnnn to code to test result). `traceability` must report zero gaps before ship.
8. P0 before P1 before P2. Never trade a P0 for a P2.

Pause policy: do not stop for approval except (a) genuine blockers, and (b) the single decision checkpoint at the end of Phase 3, where all open technology choices are presented together.

Phase 3 decisions to cover at minimum: backend framework and language (default Python FastAPI + SQLAlchemy + Alembic); frontend (default Next.js/React + Tailwind + a component library); Postgres version, migration tool; MCP SDK and transport (stdio for Claude Code, streamable HTTP for the app); agent orchestration (plain orchestrator code); job scheduling for the daily run and promise checks; LLM: OpenRouter to Claude Haiku 4.5, configurable model id; demo hosting target (local Docker Compose mandatory; hosted optional).

Phase 5 design intent: a professional collections operations console (modern fintech back-office), not a chatbot. Dense but calm tables, clear status badges, a strong vertical timeline, INR formatting everywhere, Indian date formats (`05 Oct 2026`), light and dark themes.

Phase 7 required make targets: `make up`, `make down`, `make migrate`, `make seed`, `make reset-demo`, `make test`, `make lint`, `make typecheck`, `make eval`, `make check` (lint + typecheck + test + eval-replay), `make demo`.

Phase 8 build order (strict):
- P0: DB + migrations, seed, customers/invoices, deterministic priority, LLM gateway (replay mode first), MCP tools, bounded agent, drafting, amount/invoice guardrails, approval queue, MailHog, reply classification, promise/dispute handling, timeline, dashboard, evals.
- P1: payment verification against ledger, promise tracking + today's promises, simulated payment + reconciliation feed, explainable priority, trajectory viewer, kill switch + admin.
- P2: WhatsApp (simulated adapter), payment link page, CRM list view, Prepare Call, autonomy modes.
- Feature flags for P2 features (WhatsApp, voice, payment link, Trusted mode).

Phase 10 deployment: Local (mandatory): `docker compose up` brings up `postgres`, `mailhog` (UI :8025, SMTP :1025), `api`, `mcp`, `worker`, `web`. `make migrate seed` then `make demo`. Works from a clean checkout with only Docker installed. Hosted demo (optional): single VM or container platform; same compose file with a production override; MailHog internal, behind basic auth; `LLM_MODE=replay` as fallback. Rollback: previous image tag + `make reset-demo`. Runbook `docs/runbooks/demo-day.md` covers reset, kill switch, MailHog down, LLM budget exhausted, fall back to replay mode.

## 4. Product requirements

### 4.1 Core workflow

Customer owes money → system lists unpaid invoices → **deterministic** priority picks who needs attention and **why** → agent reads customer history → selects action, channel and tone → drafts message → **guardrails verify every invoice number, amount, total, customer and date against the DB** → human Approves / Edits / Rejects → send via MailHog (or simulated WhatsApp) → customer reply ingested → classified (promise / part payment / dispute / statement request / payment confirmation / no intent / noise) → recorded → promise tracked → payment arrives? YES → reconcile and close/update invoice; NO → promise missed → follow-up recommended; dispute → human escalation.

### 4.2 Entities

- **Customer:** name, email, phone, segment, credit terms, total outstanding (derived), risk/priority (derived), interactions, promises, missed promises, disputes, payment history.
- **Invoice:** number, customer, invoice date, due date, amount, amount paid (derived from allocations), amount remaining (derived), status (`unpaid`, `partially_paid`, `paid`, `disputed`), days overdue (derived from the demo clock).
- **Payment**, **PaymentAllocation**, **Promise** (`pending`/`fulfilled`/`partially_fulfilled`/`missed`), **Dispute** (`open`/`resolved`), **Message** (channel, tone, status: `draft`/`pending_approval`/`approved`/`rejected`/`sent`/`failed`), **Reply**, **Escalation**, **TimelineEvent**, **AgentRun**, **AgentStep**, **GuardrailEvent**, **LlmCall** (tokens, cost), **Settings** (kill switch, autonomy mode, budget).

### 4.3 Daily collection run

- Seed: **50 customers, 300 invoices, 40 replies** (deterministic, fixed RNG seed).
- **Demo clock:** a configurable `DEMO_TODAY` (default `2026-09-30`, Asia/Kolkata). All "days overdue", "due today" and promise checks use it. Admin can advance the clock by N days, essential for showing a promise fulfilled/missed live.
- Priority is computed in application code (never by the LLM) from: amount overdue, oldest days overdue, missed promises, count of overdue invoices, dispute status, segment. Select **top 15**.

### 4.4 Explainable priority

Each prioritised customer shows the score, the band (HIGH/MEDIUM/LOW) and the **reason codes** that produced it, e.g. "High outstanding (₹7,50,000)", "Oldest invoice 19 days overdue", "1 missed promise". Reasons come from the scoring function, not the LLM.

### 4.5 Timeline (a flagship UI element)

Every state change writes a `TimelineEvent`: invoice due, reminder drafted, guardrail passed/failed, approved/edited/rejected, sent, reply received, classification, promise logged, payment received/matched, promise fulfilled/missed, dispute opened, escalation created. The customer page renders it chronologically with icons, amounts and actors (AI / human / system / customer).

### 4.6 MCP server

Required tools: `list_overdue`, `get_customer_history`, `draft_message`, `send_message`, `log_promise`, `log_dispute`, `escalate`.
Useful additions: `get_invoice`, `get_customer`, `record_payment`, `check_promise_status`, `create_followup`, `classify_reply`.
Every tool: JSON-schema input and output, validation, typed error codes, no raw SQL, no unrestricted DB access. `send_message` **refuses** unless the message is `approved` (or allow-listed under Trusted mode) and the kill switch is off.

### 4.7 Bounded agent

Max **4 tool calls per customer per run**. On limit: stop, record `STOPPED_LIMIT` with reason. No agent-to-agent recursion. Logical roles behind one orchestrator: **Collections**, **Reply Understanding**, **Payment Verification**, **Escalation**.

### 4.8 Trajectory log

Per run: run id, customer, timestamps, each tool + arguments (PII redacted) + result summary, action selected, reason, tool-call count, final outcome (e.g. `WAIT_FOR_APPROVAL`, `ESCALATED`, `STOPPED_LIMIT`, `NO_ACTION`). Viewable in UI.

### 4.9 Drafting and amount verification

Drafts cite exact invoices ("INV-1021 | ₹4,00,000 | due 10 Sep 2026") and the total. Before saving: extract invoice numbers, amounts (handle `₹4,00,000`, `Rs 4 lakh`, `4L`, `400000`), dates and customer name; verify each against the DB; verify the total; **reject on any mismatch** and log a `GuardrailEvent`. Preferred approach: the LLM writes prose around **placeholders** (`{{invoice_table}}`, `{{total}}`) that the application fills from the DB, then the verifier still runs on the final text.

### 4.10 Tone and language safety

Tones: gentle, firm, final, selected deterministically from history and ageing. Guardrail rejects threats, abuse, harassment, legal threats not configured by the business, contacting third parties, shaming, false urgency and anything implying consequences not in policy.

### 4.11 Approval queue

Shows customer, outstanding, invoices, days overdue, priority reasons, tone, channel, draft, trajectory. Actions: Approve / Edit / Reject (with reason). **Edited drafts are re-verified by guardrails before they can be approved.**

### 4.12 Messaging

`MessageChannel` interface with `EmailChannel` (SMTP → MailHog), `WhatsAppChannel` (simulated, provider-pluggable), `VoiceChannel` (call-prep only). Idempotent send (one send per approved message).

### 4.13 Reply classification

Classes: PROMISE, PART_PAYMENT, DISPUTE, STATEMENT_REQUEST, PAYMENT_CONFIRMATION, NO_INTENT_UNCLEAR, OTHER_NOISE. Output: class, amount (paise), date (resolved against demo clock), invoice refs, confidence, recommended action. Extracted amounts/dates are **parsed and validated in code**; low confidence → human review. Treat reply text as untrusted input (prompt-injection defence).

### 4.14 Disputes

Detect reason + invoice, `log_dispute`, mark invoice `disputed`, pause reminders on that invoice, `escalate`. Never argue with the customer.

### 4.15 Payment verification and reconciliation

"We already paid ₹5 lakh" → check ledger → match (amount/reference/date window) or flag discrepancy → human verifies. Simulated bank feed (via the webhook handler) auto-matches when unambiguous, otherwise "Needs human verification". Never mark paid on a customer claim alone.

### 4.16 Promises

Store customer, amount, date, invoices, status. "Today's promises" panel with [Check payment]. Missed → ⚠ badge + recommended next action.

### 4.17 Dashboard

Total outstanding, total overdue, customers overdue, today's promises, missed promises, open disputes, pending approvals, high-risk customers, ageing buckets (0–30, 31–60, 61–90, 90+), and **"What needs my attention today?"** (🔴 high-priority, 🟠 missed promises, 🟡 disputes, 🟢 approved reminders ready).

### 4.18 Customer detail page

Info, outstanding, invoices, priority explanation, timeline, payments, promises, disputes, messages, trajectory, pending approvals, recommended next action.

### 4.19 P2 extensions

Simulated WhatsApp; DEMO payment link page (clearly labelled SIMULATED) that creates a payment and updates invoices; CRM list (name, outstanding, overdue, priority, last contact, next action); Prepare Call (summary, invoices, prior promises, talking points); autonomy modes **Manual (default) / Assisted (batch approval) / Trusted (only allow-listed gentle reminders auto-send)**.

### 4.20 LLM gateway

One function for all model calls: OpenRouter, Claude Haiku 4.5 (configurable id), `max_tokens ≤ 500`, token + cost logging, running total, refuse after budget, retries with backoff, timeouts, `LLM_MODE=live|replay|record`. Replay fixtures keyed by prompt-version + input hash.

### 4.21 Kill switch and admin

Global pause: analysis continues, **no send path works** (enforced in `send_message`, the worker and the API). Admin: toggle sending, autonomy mode, view status, cost, runs, guardrail failures, advance demo clock, reset demo data.

### 4.22 Evaluation

- **40 labelled replies:** classification accuracy, expected-action accuracy, amount extraction, date extraction, computed from real runs, never hand-written.
- **≥ 10 trajectory scenarios:** input, expected class, expected tool sequence, expected final action; run automatically.
- **Guardrail red-team set:** drafts with invented amounts, wrong totals, wrong customer, nonexistent invoices, threatening tone; all must be rejected.
- Report in `docs/evals/report.md` and an **Evaluation** page in the UI. CI runs in replay mode.

### 4.23 Seed data

Realistic Indian B2B names (ABC Distributors, Sri Lakshmi Industries, Kumar Electricals, Andhra Industrial Supplies, Metro Wholesale, …), INR amounts from ₹15,000 to ₹25,00,000, mix of: huge overdue, recently overdue, paid, partially paid, disputed, broken promises, clean customers. Emails use `@example.in`-style demo domains only.

### 4.24 Main demo story (must be flawless)

**ABC Distributors**: ₹7,50,000 outstanding across 3 overdue invoices, 1 missed promise → selected with reasons → AI drafts → guardrail verifies → human approves → MailHog shows it → reply: "We can pay ₹3 lakh on October 5 and the remaining amount later." → PROMISE ₹3,00,000 on 05 Oct → advance demo clock → simulated bank payment ₹3,00,000 arrives → auto-matched → outstanding ₹4,50,000, promise fulfilled → customer disputes another invoice → DISPUTE detected → escalation created → timeline shows everything.

Provide `make demo` (or a script) that resets data to the start of this story.

## 5. HLD: required content

Layers kept strictly separate:

| Layer | Responsibility | May call |
|---|---|---|
| Data | Postgres ledger, derived views | none |
| Tools | MCP server (only door for the agent) | Data (via services) |
| Intelligence | Orchestrator + roles, prompts | LLM gateway, Tools |
| LLM gateway | All model calls, cost, replay | OpenRouter |
| Safety | Deterministic guardrails + policy | Data (read-only) |
| Action | Approval workflow, autonomy modes, kill switch | Safety, Messaging |
| Messaging | Channel adapters | MailHog / simulated |
| Payment | Ledger, simulated feed, reconciliation | Data |
| Evaluation | Replay fixtures, labelled sets, reports | Intelligence (replay) |
| UI / API | Dashboard, workspace, admin | API services only |

Include: C4 container diagram; sequence diagrams for (a) daily run → draft → approval → send, (b) reply → classify → promise/dispute, (c) bank feed → reconcile → promise fulfilled; failure-mode table (LLM down → replay/skip, budget exhausted, MailHog down → message `failed` + retry, guardrail reject, duplicate webhook, kill switch on); trust boundaries (customer reply text is untrusted).

## 6. LLD: required content

- Module/folder layout and ownership.
- DDL for every table, indexes, constraints (money as `BIGINT` paise, `CHECK` constraints on status enums, derived amounts via views or trigger-free service functions).
- State machines: Invoice, Message, Promise, Dispute, Escalation, AgentRun.
- Priority formula with weights, normalisation and reason-code mapping (unit-tested with fixtures).
- MCP tool specs: name, input/output JSON schema, errors, side effects, idempotency.
- Guardrail algorithms: amount/Indian-number parser, invoice-number regex, total check, customer-name check, date check, tone lexicon + LLM-free rules, approval check, loop-limit check, ledger-evidence check.
- Gateway interface, pricing table, budget accounting, replay key format.
- Channel adapter interface and MailHog SMTP config.
- Job specs: daily run, promise check, send worker (idempotency keys).
- API endpoints (matching `openapi.yaml`) and error format.
- Env var table: `DATABASE_URL`, `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_MODE`, `LLM_BUDGET_USD`, `LLM_MAX_TOKENS`, `SMTP_HOST`, `SMTP_PORT`, `MAILHOG_UI_URL`, `DEMO_TODAY`, `TZ`, `SENDING_ENABLED`, `AUTONOMY_MODE`, `ADMIN_TOKEN`, `FEATURE_WHATSAPP`, `FEATURE_VOICE`, `FEATURE_PAYMENT_LINK`.

## 7. Guardrails checklist (each must have a test and log a GuardrailEvent on failure)

Invented amount · nonexistent invoice · invoice of another customer · wrong total · wrong customer name · wrong/impossible date · unsafe tone · send without approval · send while kill switch on · edited draft not re-verified · tool call beyond limit · direct DB access attempt · payment marked on claim without ledger evidence · prompt injection in reply text · LLM call over budget.

## 8. Final deliverables

Working app · Docker Compose · migrations · seed + `reset-demo` · MCP server (with Claude Code registration snippet) · bounded agent · LLM gateway · guardrails · approval system · MailHog flow · reply classifier · payment simulation + reconciliation · dashboard · customer timeline · trajectory viewer · evaluation framework + report · tests · PRD, backlog, ADRs, HLD, LLD, ERD, OpenAPI, threat model, traceability matrix · README.

The README must contain these sections, verified by actually following them:

1. How to run: exact commands from a clean checkout.
2. How to demo: a 5 to 10 minute click-by-click script of the 4.24 story, with timings and a fallback line for each step (e.g. "if LLM unavailable, set `LLM_MODE=replay`").
3. What is real vs simulated: table: Postgres, MCP, agent, guardrails, OpenRouter (real); MailHog (real SMTP, test inbox); WhatsApp, bank feed, payment link, voice (simulated).
4. Architecture: the layer diagram and a one-paragraph plain-language data flow.
5. Evaluation results: numbers copied from the generated report, with the command that produced them.
6. Environment variables: the table from the LLD.

Finish with `task-report`: Changed / Verified / Not done / Noticed, plus the exact `git push` and MR commands for the engineer to run.
