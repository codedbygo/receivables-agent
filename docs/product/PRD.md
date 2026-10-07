# PRD: AI Receivables Collections Agent

Source: `docs/product/brief.md` (master prompt pasted 2026-09-30; sections 0, 4 to 8), with `docs/discovery/office-hours.md` for non-goals marked inferred.   Normalised: 2026-09-30
Owner: unconfirmed: Savitha Sista (engineer on HACK-001)   Tracker epic: unconfirmed: HACK-001 (tracker: none)

## 1. Problem

Indian B2B companies carry unpaid invoices that need chasing; the product is "an AI employee that manages unpaid invoices" (brief 0, Mission). Its behaviour must be demonstrated, measured, audited and trusted (brief 0, Mission), which rules out an agent that computes or invents money (brief 0.2) or sends without human approval (brief 0.3).

The brief gives no numbers for the problem today (DSO, hours spent, missed promises). inferred: from office-hours, collections today run on Tally ageing reports, spreadsheets, phone and WhatsApp, with promises tracked by hand.

## 2. Business objectives

| Id | Objective | Target (measurable) | Source |
| --- | --- | --- | --- |
| B1 | Overdue customers get the right follow-up without manual chasing: prioritised, drafted, sent after approval, replies understood | target: unconfirmed | brief 0 Mission, 4.1 |
| B2 | No outbound message carries a wrong invoice, amount, total, customer or date | 100% of the guardrail red-team set rejected ("all must be rejected") | brief 4.22, 7 |
| B3 | A human stays in control of every send, and sending can be stopped instantly | target: unconfirmed | brief 0.3, 4.21 |
| B4 | The agent's behaviour is measured and auditable | eval accuracy reported from real runs; target: unconfirmed | brief 0 Mission, 4.8, 4.22 |
| B5 | The ABC Distributors demo story runs end to end without failure | "must be flawless"; target: unconfirmed (no time or count given) | brief 4.24 |

## 3. Non-goals

- Real telephony: voice is call-prep only (brief 4.12, Phase 6 "no real telephony").
- A real WhatsApp provider: WhatsApp is simulated and provider-pluggable (brief 4.12, 4.19).
- A real payment gateway or bank connection: payment link and bank feed are simulated (brief 4.15, 4.19).
- inferred: import from Tally or other accounting systems; seed data only (office-hours). Q-017.
- inferred: regional-language drafts (Hindi, Telugu, Tamil) (office-hours). Q-018.
- inferred: multi-tenancy and SSO; one business, three roles (office-hours). Q-014.

## 4. Personas

| Persona | Group | Who they are | What they need | Source |
| --- | --- | --- | --- | --- |
| Collector | 00 end user | the human who approves, edits or rejects drafts and handles escalations | see who needs attention and why, trust every number in a draft, act in one place | brief 4.1 ("human Approves / Edits / Rejects"), Phase 4 role matrix |
| Admin | 01 admin | runs the system and the demo | toggle sending, autonomy mode, see cost, runs and guardrail failures, move the demo clock, reset data | brief 4.21 |
| Viewer | 00 end user | read-only user | see dashboard and customers without acting | brief Phase 4 role matrix (`viewer`) |
| Customer | 03 integration | the B2B buyer who owes money and replies | receive correct, polite reminders; have promises, disputes and payments recorded | brief 4.1, 4.13 |
| MCP client (Claude Code) | 03 integration | an external agent host calling the MCP tools | schema-checked tools with typed errors | brief 4.6, 8 |

## 5. Requirement statements

One testable statement per id. Ids are never reused or renumbered. Tier is the build tier from the brief's Phase 8 order (P0, P1, P2).

| Id | Statement | Persona | Tier | Source | Flags |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | The system lists each customer's unpaid invoices. | Collector | P0 | 4.1 | none |
| REQ-002 | The system stores every money amount as integer paise. | none | P0 | 0.2 | none |
| REQ-003 | The system formats money as INR with Indian digit grouping (`₹7,50,000`) only at the display edge. | Collector | P0 | 0.2, Phase 5 | none |
| REQ-004 | Every money amount, total and rounding in a message or screen is computed by application code from the ledger, never by the LLM. | none | P0 | 0.2 | none |
| REQ-005 | The system stores for each customer: name, email, phone, segment and credit terms. | Collector | P0 | 4.2 | none |
| REQ-006 | The system derives each customer's total outstanding from the ledger. | Collector | P0 | 4.2 | none |
| REQ-007 | The system stores for each invoice: number, customer, invoice date, due date and amount. | Collector | P0 | 4.2 | none |
| REQ-008 | The system derives an invoice's amount paid from payment allocations and its amount remaining from amount minus amount paid. | Collector | P0 | 4.2 | none |
| REQ-009 | An invoice's status is one of unpaid, partially_paid, paid, disputed. | Collector | P0 | 4.2 | none |
| REQ-010 | The system derives an invoice's days overdue from the demo clock. | Collector | P0 | 4.2, 4.3 | none |
| REQ-011 | The system records payments and their allocations to invoices. | Collector | P1 | 4.2 | none |
| REQ-012 | A promise's status is one of pending, fulfilled, partially_fulfilled, missed. | Collector | P0 | 4.2 | none |
| REQ-013 | A dispute's status is one of open, resolved. | Collector | P0 | 4.2 | none |
| REQ-014 | A message records its channel, tone and a status of draft, pending_approval, approved, rejected, sent or failed. | Collector | P0 | 4.2 | none |
| REQ-015 | The system stores customer replies and escalations. | Collector | P0 | 4.2 | none |
| REQ-016 | The system records each LLM call with its tokens and cost. | Admin | P0 | 4.2, 4.20 | none |
| REQ-017 | The system persists settings for kill switch, autonomy mode and LLM budget. | Admin | P1 | 4.2, 4.21 | none |
| REQ-018 | The seed creates 10 customers, 60 invoices and 20 replies from a fixed RNG seed, identical on every run (HACK-006; was 50, 300 and 40). | Admin | P0 | 4.3 | none |
| REQ-019 | Seed customers carry realistic Indian B2B names and invoice amounts between ₹15,000 and ₹25,00,000. | Admin | P0 | 4.23 | none |
| REQ-020 | The seed includes customers that are hugely overdue, recently overdue, paid, partially paid, disputed, with broken promises, and clean. | Admin | P0 | 4.23 | none |
| REQ-021 | Seed email addresses use `@example.in`-style demo domains only. | Admin | P0 | 4.23 | none |
| REQ-022 | All days-overdue, due-today and promise checks use a demo clock `DEMO_TODAY`, default 2026-09-30 in Asia/Kolkata. | Admin | P0 | 4.3 | none |
| REQ-023 | An admin advances the demo clock by N days. | Admin | P1 | 4.3, 4.21 | none |
| REQ-024 | An admin resets demo data to the seeded state. | Admin | P1 | 4.21 | none |
| REQ-025 | `make demo` resets data to the start of the ABC Distributors story. | Admin | P0 | 4.24 | none |
| REQ-026 | Application code computes a priority score from amount overdue, oldest days overdue, missed promises, count of overdue invoices, dispute status and segment. | Collector | P0 | 4.3 | none |
| REQ-027 | The daily collection run selects the top 15 customers by priority. | Collector | P0 | 4.3 | none |
| REQ-028 | Each prioritised customer shows its score, its band (HIGH, MEDIUM, LOW) and the reason codes the scoring function produced. | Collector | P1 | 4.4 | none |
| REQ-029 | The agent reads the customer's history before selecting an action. | none | P0 | 4.1 | none |
| REQ-030 | The agent selects an action, a channel and a tone for each selected customer. | none | P0 | 4.1 | none |
| REQ-031 | Application code selects the tone (gentle, firm, final) from history and ageing. | none | P0 | 4.10 | none |
| REQ-032 | The agent makes at most 4 tool calls per customer per run; on reaching the limit it stops and records `STOPPED_LIMIT` with a reason. | none | P0 | 0.4, 4.7 | none |
| REQ-033 | The agent never invokes another agent. | none | P0 | 4.7 | none |
| REQ-034 | One orchestrator runs the Collections, Reply Understanding, Payment Verification and Escalation roles. | none | P0 | 4.7 | none |
| REQ-035 | Each agent run records run id, customer, timestamps, each tool with arguments and a result summary, action selected, reason, tool-call count and final outcome (`WAIT_FOR_APPROVAL`, `ESCALATED`, `STOPPED_LIMIT`, `NO_ACTION`). | Collector | P0 | 4.8 | none |
| REQ-036 | Tool arguments in the trajectory log have PII redacted. | Collector | P0 | 4.8 | none |
| REQ-037 | A collector views an agent run's trajectory in the UI. | Collector | P1 | 4.8 | none |
| REQ-038 | The MCP server exposes `list_overdue`, `get_customer_history`, `draft_message`, `send_message`, `log_promise`, `log_dispute` and `escalate`. | MCP client | P0 | 4.6 | none |
| REQ-039 | The MCP server exposes `get_invoice`, `get_customer`, `record_payment`, `check_promise_status`, `create_followup` and `classify_reply`. | MCP client | P1 | 4.6 ("useful additions") | none |
| REQ-040 | Every MCP tool validates its input and output against a JSON schema. | MCP client | P0 | 4.6 | none |
| REQ-041 | Every MCP tool reports failures with a typed error code. | MCP client | P0 | 4.6 | none |
| REQ-042 | No MCP tool accepts raw SQL or gives unrestricted database access. | MCP client | P0 | 4.6, 7 | none |
| REQ-043 | `send_message` refuses unless the message is approved (or allow-listed under Trusted mode) and the kill switch is off. | MCP client | P0 | 4.6 | none |
| REQ-044 | The MCP server serves stdio for Claude Code and streamable HTTP for the app. | MCP client | P0 | Phase 3 | none |
| REQ-045 | The repository provides a Claude Code registration snippet for the MCP server. | MCP client | P0 | 8 | none |
| REQ-046 | A draft cites each invoice's number, amount and due date, and the total. | Customer | P0 | 4.9 | none |
| REQ-047 | The LLM writes draft prose around placeholders (`{{invoice_table}}`, `{{total}}`) that application code fills from the database. | none | P0 | 4.9 ("preferred approach") | none |
| REQ-048 | Before a draft is saved, the system extracts invoice numbers, amounts (including `₹4,00,000`, `Rs 4 lakh`, `4L`, `400000`), dates and customer name from the final text. | none | P0 | 4.9 | none |
| REQ-049 | The system rejects a draft whose extracted invoice numbers, amounts, dates or customer name do not match the database, or whose total does not match, and logs a GuardrailEvent. | Collector | P0 | 4.9, 7 | none |
| REQ-050 | The system rejects a draft that cites an invoice belonging to another customer. | Collector | P0 | 7 | none |
| REQ-051 | The system rejects a draft containing an impossible date. | Collector | P0 | 7 | none |
| REQ-052 | The system rejects a draft containing threats, abuse, harassment, legal threats not configured by the business, contact with third parties, shaming, false urgency or consequences not in policy. | Customer | P0 | 4.10 | ambiguous: Q-006 |
| REQ-053 | Every guardrail failure writes a GuardrailEvent. | Admin | P0 | 7 | none |
| REQ-054 | Each of the 15 guardrail cases in brief section 7 has an automated test. | none | P0 | 7 | none |
| REQ-055 | The approval queue shows customer, outstanding, invoices, days overdue, priority reasons, tone, channel, draft and trajectory. | Collector | P0 | 4.11 | none |
| REQ-056 | A collector approves, edits or rejects a draft; a rejection requires a reason. | Collector | P0 | 4.11 | none |
| REQ-057 | An edited draft passes the guardrails again before it can be approved. | Collector | P0 | 4.11, 7 | none |
| REQ-058 | Every outbound message requires human approval, except allow-listed messages under Trusted mode. | Collector | P0 | 0.3 | none |
| REQ-059 | An approved email message is sent over SMTP to the MailHog test inbox. | Customer | P0 | 4.12 | none |
| REQ-060 | A WhatsApp channel sends through a simulated, provider-pluggable adapter. | Customer | P2 | 4.12, 4.19 | none |
| REQ-061 | A voice channel produces call preparation only and places no call. | Collector | P2 | 4.12 | none |
| REQ-062 | An approved message is sent at most once. | Customer | P0 | 4.12 | none |
| REQ-063 | The system ingests a customer reply against the customer and message it answers. | Customer | P0 | 4.1 | none (ingestion path: Q-007) |
| REQ-064 | The system classifies a reply as PROMISE, PART_PAYMENT, DISPUTE, STATEMENT_REQUEST, PAYMENT_CONFIRMATION, NO_INTENT_UNCLEAR or OTHER_NOISE. | Collector | P0 | 4.13 | none |
| REQ-065 | A classification returns class, amount in paise, date resolved against the demo clock, invoice references, confidence and recommended action. | Collector | P0 | 4.13 | none |
| REQ-066 | Amounts and dates extracted from a reply are parsed and validated by application code. | none | P0 | 4.13 | none |
| REQ-067 | A classification with low confidence goes to human review. | Collector | P0 | 4.13 | ambiguous: Q-001 |
| REQ-068 | Reply text is treated as untrusted input and instructions inside it cannot change the agent's tools, policy or outputs. | none | P0 | 4.13, 7 | none |
| REQ-069 | The system stores each promise with customer, amount, date, invoices and status. | Collector | P0 | 4.16 | none |
| REQ-070 | A "Today's promises" panel lists promises due on the demo date with a Check payment action. | Collector | P1 | 4.16 | none |
| REQ-071 | A missed promise shows a warning badge and a recommended next action. | Collector | P1 | 4.16, 4.1 | none |
| REQ-072 | On a dispute the system records its reason and invoice through `log_dispute` and marks the invoice disputed. | Collector | P0 | 4.14 | none |
| REQ-073 | The system drafts no reminders for a disputed invoice while the dispute is open. | Customer | P0 | 4.14 | none |
| REQ-074 | A dispute creates an escalation to a human. | Collector | P0 | 4.14, 4.1 | none |
| REQ-075 | The system never sends the customer an argument about a disputed invoice. | Customer | P0 | 4.14 | ambiguous: Q-005 |
| REQ-076 | A customer's payment claim is checked against the ledger by amount, reference and date window, and either matched or flagged as a discrepancy for human verification. | Collector | P1 | 4.15 | ambiguous: Q-003 |
| REQ-077 | A simulated bank feed arrives through the webhook handler and auto-matches a payment when exactly one match exists; otherwise the payment is marked "Needs human verification". | Collector | P1 | 4.15 | none |
| REQ-078 | The system never marks an invoice paid on a customer claim alone. | Collector | P1 | 4.15, 7 | none |
| REQ-079 | A matched payment updates the invoices it is allocated to, closing any it pays in full. | Collector | P1 | 4.1 | none (allocation: Q-012) |
| REQ-080 | A promise becomes fulfilled when matched payments cover its amount by its date, and missed when they do not. | Collector | P1 | 4.1, 4.24 | ambiguous: Q-004 |
| REQ-081 | Every state change listed in brief 4.5 writes a TimelineEvent. | Collector | P0 | 4.5 | none |
| REQ-082 | The customer page renders timeline events in time order with icon, amount and actor (AI, human, system, customer). | Collector | P0 | 4.5 | none |
| REQ-083 | The dashboard shows total outstanding, total overdue, customers overdue, today's promises, missed promises, open disputes, pending approvals and high-risk customers. | Collector | P0 | 4.17 | none |
| REQ-084 | The dashboard shows ageing buckets 0 to 30, 31 to 60, 61 to 90 and 90+ days. | Collector | P0 | 4.17 | none |
| REQ-085 | The dashboard shows "What needs my attention today?" grouping high-priority customers, missed promises, disputes and approved reminders ready. | Collector | P0 | 4.17 | none |
| REQ-086 | The customer detail page shows info, outstanding, invoices, priority explanation, timeline, payments, promises, disputes, messages, trajectory and pending approvals. | Collector | P0 | 4.18 | none |
| REQ-087 | The customer detail page shows a recommended next action. | Collector | P0 | 4.18 | none |
| REQ-088 | A demo payment link page, labelled SIMULATED, creates a payment and updates invoices. | Customer | P2 | 4.19 | none |
| REQ-089 | A CRM list shows each customer's name, outstanding, overdue, priority, last contact and next action. | Collector | P2 | 4.19 | none |
| REQ-090 | Prepare Call shows a summary, invoices, prior promises and talking points for a customer. | Collector | P2 | 4.19 | none |
| REQ-091 | The autonomy mode is Manual (default), Assisted (batch approval) or Trusted (only allow-listed gentle reminders auto-send). | Admin | P2 | 4.19 | ambiguous: Q-008, Q-009 |
| REQ-092 | WhatsApp, voice, payment link and Trusted mode are behind feature flags that an admin can switch off. | Admin | P2 | Phase 8 | none |
| REQ-093 | Every model call goes through one gateway function that calls OpenRouter with a configurable model id, default Claude Haiku 4.5. | none | P0 | 4.20 | none |
| REQ-094 | The gateway caps `max_tokens` at 500. | none | P0 | 4.20 | none |
| REQ-095 | The gateway logs tokens and cost per call and keeps a running total. | Admin | P0 | 4.20 | none |
| REQ-096 | The gateway refuses calls once the budget is exhausted and logs a GuardrailEvent. | Admin | P0 | 4.20, 7 | none |
| REQ-097 | The gateway retries with backoff and enforces timeouts. | none | P0 | 4.20 | none |
| REQ-098 | The gateway runs in `live`, `replay` or `record` mode; replay fixtures are keyed by prompt version and input hash. | none | P0 | 4.20 | none |
| REQ-099 | With the kill switch on, analysis continues and no send path works, enforced in `send_message`, the worker and the API. | Admin | P1 | 4.21 | none |
| REQ-100 | An admin toggles sending and autonomy mode and views status, cost, runs and guardrail failures. | Admin | P1 | 4.21 | none |
| REQ-101 | An evaluation over 40 labelled replies reports classification accuracy, expected-action accuracy, amount extraction and date extraction, computed from real runs. | Admin | P0 | 4.22 | none |
| REQ-102 | At least 10 trajectory scenarios (input, expected class, expected tool sequence, expected final action) run automatically. | Admin | P0 | 4.22 | none |
| REQ-103 | Every draft in the guardrail red-team set (invented amounts, wrong totals, wrong customer, nonexistent invoices, threatening tone) is rejected. | Admin | P0 | 4.22 | none |
| REQ-104 | Evaluation results are written to `docs/evals/report.md` and shown on an Evaluation page in the UI. | Admin | P0 | 4.22 | none |
| REQ-105 | CI runs the evaluation in replay mode. | none | P0 | 4.22 | none |
| REQ-106 | The test suite passes with no OpenRouter key, no network and no real mail, WhatsApp or bank. | none | P0 | 0.5 | none |
| REQ-107 | `docker compose up` from a clean checkout with only Docker installed starts postgres, mailhog, api, mcp, worker and web. | Admin | P0 | Phase 10 | none |
| REQ-108 | The Makefile provides `up`, `down`, `migrate`, `seed`, `reset-demo`, `test`, `lint`, `typecheck`, `eval`, `check` (lint, typecheck, test, eval-replay) and `demo`. | Admin | P0 | Phase 7 | none |
| REQ-109 | The README contains How to run, How to demo, What is real vs simulated, Architecture, Evaluation results and Environment variables, each verified by following it. | Admin | P0 | 8 | none |
| REQ-110 | The ABC Distributors story in brief 4.24 runs end to end: selection with reasons, draft, guardrail pass, approval, MailHog delivery, promise ₹3,00,000 on 05 Oct, clock advance, ₹3,00,000 bank payment auto-matched, outstanding ₹4,50,000, promise fulfilled, dispute detected, escalation, full timeline. | Collector | P0 | 4.24 | none (data shape: Q-011) |
| REQ-111 | Users sign in with one of three roles, admin, collector or viewer, and each role can do only what the role matrix allows. | Admin | P1 | Phase 4 (auth) | none (mechanism: Q-014) |
| REQ-112 | The api exposes `/healthz` and `/readyz`. | Admin | P1 | Phase 7 | none |
| REQ-113 | Logs are structured JSON and contain no PII message bodies. | Admin | P1 | Phase 7 | none |
| REQ-114 | Dates display in Indian format (`05 Oct 2026`). | Collector | P0 | Phase 5 | none |
| REQ-115 | The UI offers light and dark themes. | Collector | P1 | Phase 5 | none |
| REQ-116 | The inbound bank-feed webhook verifies a signature and rejects requests outside a replay window. | none | P1 | Phase 4 (webhooks) | none |
| REQ-117 | The daily collection run and the promise check run as scheduled jobs. | Admin | P0 | Phase 3 | none (trigger: Q-010) |
| REQ-118 | A missed promise produces a recommended follow-up. | Collector | P1 | 4.1 | none |
| REQ-119 | A statement request produces a recommended action to send a statement of open invoices. | Collector | P1 | 4.1, 4.13 | inferred: Q-019 |
| REQ-120 | The system counts `OPENROUTER_API_KEY` as a secret: it is never committed and `.env.example` lists every variable. | Admin | P0 | 0.5, Phase 7 | none |
| REQ-121 | A collector or admin creates a distributor (name, email, phone, segment, credit terms) and edits those details; names are unique ignoring case and each change is on the timeline (HACK-007). | Collector | P1 | HACK-007 | none |
| REQ-122 | A collector or admin adds an unpaid invoice (unique INV- number, invoice and due dates, amount above zero) to a distributor (HACK-007). | Collector | P1 | HACK-007 | none |
| REQ-123 | A collector or admin uploads a CSV of distributors and invoices; any bad row saves nothing and the errors name the row; at most 500 rows and 1 MB (HACK-007). | Collector | P1 | HACK-007 | none |
| REQ-124 | Only an admin deletes a distributor, which removes every row recorded about it in one transaction (HACK-007). | Admin | P1 | HACK-007 | none |
| REQ-125 | With real SMTP, an address listed in EMAIL_ALLOW_REAL receives its mail; every other address still goes to the demo inbox (HACK-007). | Admin | P1 | HACK-007 | none |
| REQ-126 | An admin connects one company Google account; its refresh token is stored encrypted and the sign-in round trip is protected by a signed, expiring state (HACK-009). | Admin | P1 | HACK-009 | none |
| REQ-127 | With EMAIL_PROVIDER=gmail, approved emails are sent from the connected account through the Gmail API and keep their thread id (HACK-009). | Admin | P1 | HACK-009 | none |
| REQ-128 | Customer emails in threads the app started are queued without their quoted history; a collector accepts one (classified like a pasted reply) or dismisses it (HACK-009, closes D-001). | Collector | P1 | HACK-009 | none |
| REQ-129 | Each pending promise and open follow-up task has one all-day event in the connected Google Calendar, removed when settled or closed (HACK-009). | Collector | P1 | HACK-009 | none |

## 6. Constraints

- Money as `BIGINT` paise; no floats for money (brief 0.2, 6).
- LLM: OpenRouter to Claude Haiku 4.5, id configurable; `max_tokens <= 500` (brief 4.20). Spike: id `anthropic/claude-haiku-4.5`, $1 / $5 per MTok (`docs/spikes/2026-09-30-openrouter-haiku.md`).
- Database: Postgres (brief 5, Phase 3).
- Mail: MailHog, SMTP :1025, UI :8025 (brief Phase 10). Spike proposes Mailpit on the same ports (`docs/spikes/2026-09-30-mail-catcher.md`); decided at Phase 3.
- MCP server with stdio and streamable HTTP transports (brief Phase 3).
- Plain orchestrator code, no heavy agent framework (brief Phase 3).
- Local Docker Compose mandatory; hosted demo optional (brief Phase 3, 10).
- Defaults proposed by the brief for Phase 3: Python FastAPI + SQLAlchemy + Alembic; Next.js/React + Tailwind + a component library.
- Bounded loop: 4 tool calls per customer per run; top 15 customers per run (brief 4.3, 4.7).
- Seed size 50 / 300 / 40 (brief 4.3).
- Env vars named by the brief: `DATABASE_URL`, `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_MODE`, `LLM_BUDGET_USD`, `LLM_MAX_TOKENS`, `SMTP_HOST`, `SMTP_PORT`, `MAILHOG_UI_URL`, `DEMO_TODAY`, `TZ`, `SENDING_ENABLED`, `AUTONOMY_MODE`, `ADMIN_TOKEN`, `FEATURE_WHATSAPP`, `FEATURE_VOICE`, `FEATURE_PAYMENT_LINK` (brief 6).
- The agent never pushes, merges, tags or deploys (brief 0.6).
- Build order P0, then P1, then P2 (brief 0.8, Phase 8).
- Environment: slow network on the build machine (git clone at 77 KiB/s; a `uv pip install mcp` did not finish in 5 minutes on 2026-09-30). Image and dependency choices should favour what is already cached locally.

## 7. Open questions

21 entries in docs/product/questions.md: 21 open, 16 need your confirmation (Q-001, Q-002, Q-003, Q-004, Q-005, Q-006, Q-007, Q-008, Q-009, Q-010, Q-011, Q-012, Q-014, Q-015, Q-016, Q-021).

## 8. Could not extract

- Problem evidence (numbers on current DSO, time spent, missed-promise rates): not in the input. A finance lead at a target customer can supply it.
- Business targets for B1, B3, B4, B5: not in the input. The hackathon judging criteria can supply them.
- Owner and tracker epic: not in the input; tracker is none.

## 9. Glossary

| Term | Meaning | Source |
| --- | --- | --- |
| Paise | 1/100 of a rupee; the unit every amount is stored in | 0.2 |
| Lakh (L) | 1,00,000 rupees; `Rs 4 lakh` and `4L` mean ₹4,00,000 | 4.9 |
| Crore (cr) | 1,00,00,000 rupees | convention (Indian numbering) |
| Demo clock | `DEMO_TODAY`, the date every overdue and promise computation uses; admin can advance it | 4.3 |
| Trajectory | the logged sequence of tool calls, arguments, results and outcome of one agent run | 4.8 |
| Guardrail / GuardrailEvent | a deterministic check on a draft, send or call, and the record written when it fails | 4.9, 7 |
| Kill switch | global pause that blocks every send path while analysis continues | 4.21 |
| Autonomy mode | Manual, Assisted or Trusted: how much approval a send needs | 4.19 |
| Replay mode | the gateway returns recorded model responses keyed by prompt version and input hash instead of calling OpenRouter | 4.20 |
| Promise | a customer's commitment to pay an amount by a date | 4.16 |
| Escalation | a case handed to a human (dispute, discrepancy, low confidence) | 4.1, 4.14 |
