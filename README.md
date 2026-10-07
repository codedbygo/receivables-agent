# Collections Agent

An AI receivables collections agent for Indian B2B companies: it picks who to chase and why, drafts reminders
that cite the exact invoices, checks every figure against the ledger before a human approves, reads the
customer's reply, tracks the promise, and reconciles the payment when it lands. The ledger computes every
amount; the model only writes prose around placeholders and labels replies.

## 1. How to run

From a clean checkout. You need Docker, and Node 24 with pnpm 10 to build the console (ADR-0002: the console
is built on the host and served by nginx, so no Node image is pulled).

```bash
make web-setup web-build   # install and build the console into frontend/dist
make up                    # postgres, mailpit, migrate (schema + seed), api, mcp, worker, web
```

| What | Where |
| --- | --- |
| Console | http://localhost:8080 |
| Test inbox (Mailpit, MailHog-compatible) | http://localhost:8025 |
| API | http://localhost:8000/api/v1 (health: `/api/v1/readyz`) |
| MCP (streamable HTTP, bearer `MCP_TOKEN`) | http://localhost:8001 |

No `.env` is needed for the demo: the defaults run with `LLM_MODE=replay` (no API key, no network). To use the
live model, copy `.env.example` to `.env`, set `OPENROUTER_API_KEY` and `LLM_MODE=live`, then `make up` again.

For development (Python 3.12 and uv on the host): `make setup`, then `make check` (the gate CI runs:
format, lint, types, unit tests, offline eval, console typecheck and tests). With the stack up:
`make test-integration`, `make eval` (writes `docs/evals/report.md`) and `make e2e` (the demo story in a browser).

Register the MCP server with Claude Code (stdio, from the repository root):

```bash
claude mcp add collections --env DATABASE_URL=postgresql+psycopg://collections:collections@localhost:5433/collections \
  -- uv --directory backend run python -m app.mcp --stdio
```

## 2. How to demo

The ABC Distributors story, about 8 minutes. Start with `make demo`, which resets the data to the start of the
story (demo date 30 Sep 2026). Sign in as **Admin** (on a hosted demo, enter the admin access code first).

| Time | Click | What the audience sees | If it goes wrong |
| --- | --- | --- | --- |
| 0:00 | Today | Totals, ageing, "What needs my attention today?" | Blank page: `make up` and wait for health |
| 0:45 | Customers, ABC Distributors | ₹7,50,000 across 3 overdue invoices; priority 66 HIGH with its reasons (high outstanding, oldest 19 days overdue, 1 missed promise) | Wrong figures: `make demo` |
| 1:30 | Run agent now | The run viewer: `get_customer_history`, `draft_message`, 2 of 4 tool calls, outcome Wait for approval | "run in progress": wait 5 s and retry. Model down: runs fall back to a template draft and say so |
| 2:15 | Approvals, ABC Distributors | The draft cites INV-1021, INV-1034, INV-1047 and ₹7,50,000; the guardrail report ticks every figure "matches ledger" | Try Edit: change ₹7,50,000 to ₹5,00,000 and save; it is refused with a ledger-mismatch error naming the figure |
| 3:00 | Approve | Status Approved; the worker sends it | Nothing sends: check Admin, sending must be on |
| 3:30 | Mailpit tab (:8025) | The email in the inbox | Mailpit down: the message shows Failed; Resend once it is back |
| 4:00 | ABC Distributors, Record a reply: "We can pay ₹3 lakh on October 5 and the remaining amount later." | Classified PROMISE, ₹3,00,000, 05 Oct 2026; promise logged | LLM unavailable: `LLM_MODE=replay` uses the deterministic classifier |
| 5:00 | Admin, Advance the clock, 5 days | Demo date 05 Oct 2026 | |
| 5:30 | Admin, Simulate a bank credit: ABC Distributors, 300000, "NEFT ABC Distributors UTR 4411" | Matched, allocated to INV-1021 | Needs verification: the reference must name the customer or an invoice |
| 6:15 | ABC Distributors | Outstanding ₹4,50,000; promise Fulfilled | |
| 6:45 | Record a reply: "INV-1047 was billed for 50 units but we received only 40. Please correct it." | DISPUTE on INV-1047; escalation opened; reminders on INV-1047 paused | |
| 7:30 | Timeline | Every step in order: drafted, guardrail passed, approved, sent, reply, promise, payment, promise fulfilled, dispute, escalation | |
| 8:00 | Admin, Pause all sending | The kill switch: nothing can send, analysis continues | |

**Collections employee features (HACK-003), about 6 more minutes.** Turn on Voice calls and Payment links in Admin first.

| Click | What the audience sees |
| --- | --- |
| ABC Distributors, "Why is this customer HIGH priority?" | Each factor with its value, the rule and the points it added; they add up to the score |
| ABC Distributors, Contact | Preferred and last channel, response status, next recommended channel and why (cadence day, consent, flags) |
| ABC Distributors, Customer memory | The history from rows, and the sentence the AI will use to recall the missed promise |
| Voice calls, Call with AI | A SIMULATED call (badge says no phone rang): the opening line states ₹7,50,000 from the ledger |
| Type "We can pay ₹2 lakh this Friday." then "Yes please" | Promise ₹2,00,000 for Friday recorded; statement draft waits in Approvals; summary with the next action |
| Admin, Advance the clock past Friday with no payment | Follow-up due on Today: promised, date, received ₹0, MISSED, "Contact the customer today", Why? |
| Admin, autonomy Assisted, then advance again on a new promise | A follow-up draft that recalls the promise waits for approval; Trusted mode never auto-sends it |
| Record a reply: "INV-1047 was billed for 50 units but we received only 40." | Dispute category wrong quantity, routed to Operations; Start investigation, then Resolve with a note |
| Contact, Customer portal, Create link; open it in a private window | The customer sees only their invoices; Promise to pay, Raise a dispute, Request help, Pay now (simulated) |
| CFO view | Receivables, overdue, collected this month, at risk, promises, collection rate, charts, attention list with Why? |
| AI Safety | Live counts: messages checked, amounts blocked (try the ₹5,00,000 edit), prompt attacks, approvals, automatic sends 0, kill switch |

Evaluation page: the numbers from the last `make eval`.

## Managing distributors (HACK-007)

Collectors and admins add a distributor with **Customers, Add distributor**, change one with **Edit details** on its
page and add an unpaid invoice with **Add invoice**. **Upload CSV** adds many at once, one row per invoice:

```
customer_name,email,phone,segment,credit_terms_days,invoice_number,invoice_date,due_date,amount_rupees
Riya Traders,riya@example.com,+919800000000,sme,30,INV-5001,2026-09-01,2026-09-20,125000
```

A new name creates the distributor; a known name (any case) gets the invoice and keeps its details. Dates are
YYYY-MM-DD, segment is sme, mid_market or enterprise, and amounts are rupees (up to 2 decimals). Any bad row saves
nothing and the errors name the row; at most 500 rows and 1 MB. Only an admin can **Delete** a distributor, which
removes everything recorded about it. A demo reset brings back the 10 seeded distributors and drops the rest.

To receive a real reminder, give a test distributor your own address and list it in `EMAIL_ALLOW_REAL`; every other
address still goes to the `EMAIL_REDIRECT_TO` inbox.

## 3. What is real and what is simulated

| Part | Status |
| --- | --- |
| PostgreSQL ledger, money as integer paise | Real |
| Priority score and its factor points, follow-up rules, dispute categories and routing, channel cadence | Real (deterministic code and policy/guardrails.yaml) |
| Customer memory, CFO dashboard, AI Safety Center counts | Real (computed from rows; nothing estimated or seeded in the Safety Center) |
| MCP server (14 tools, stdio and streamable HTTP) | Real |
| Bounded agent (at most 4 tool calls per customer per run, every step logged) | Real |
| Guardrails (amounts, invoices, totals, customer, dates, tone, send gate, kill switch, consent) | Real; every AI call line is verified too |
| Language model | OpenRouter (Claude Haiku 4.5) or a free local open-source model through Ollama (`LLM_PROVIDER=ollama`), in `LLM_MODE=live`; replay fixtures or deterministic fallbacks otherwise |
| Email | Real SMTP into Mailpit, a test inbox; nothing leaves the machine |
| SMS | Real and free through the open-source Android SMS Gateway app on your own phone (`SMS_GATEWAY_*`), or through Twilio; otherwise SIMULATED, labelled on every message |
| WhatsApp | Real through Twilio only (no free, compliant open-source route); otherwise SIMULATED |
| Voice calls | Real phone calls through Twilio when `TWILIO_*` and `VOICE_PUBLIC_BASE_URL` are set; otherwise SIMULATED (no phone rings). On a simulated call the browser's free Web Speech API can speak the AI lines and listen for the customer's side (Chrome, Edge). Never recorded |
| Customer portal | Real signed links, promises, disputes and help requests; Pay Now is SIMULATED (no payment processor) |
| Bank feed, payment link | Simulated: signed credits through the real webhook handler |

## 4. Architecture

```mermaid
flowchart LR
  UI[Console, React] --> API[FastAPI API]
  API --> SVC[Services: ledger, priority, approval, payments]
  W[Worker: daily run, promise check, send] --> SVC
  MCP[MCP server] --> REG[Tool registry]
  ORCH[Bounded orchestrator, 4 roles] --> REG
  ORCH --> GW[LLM gateway: budget, retries, replay]
  GW --> OR[OpenRouter]
  REG --> SVC
  SVC --> G[Guardrails]
  SVC --> DB[(PostgreSQL ledger)]
  W --> MAIL[Mailpit SMTP]
  BANK[Bank feed, signed] --> API
```

In plain words: the ledger in Postgres holds every invoice, payment and promise, and derives every balance.
Each day a deterministic score picks the customers who need attention and explains why. For each, a bounded
agent reads the customer's history through the tool registry (the only door to data) and asks the model for
prose around `{{invoice_table}}` and `{{total}}`; code fills those from the ledger, and the guardrails check
every invoice, amount, total, date, name and the tone before the draft waits for a human. Only an approved,
verified message can be sent, and only while sending is on. Replies are treated as untrusted text: the model
labels them, code parses and checks amounts and dates, and fixed rules decide what to do. Bank credits are
matched and allocated by code, never by a customer's claim. Details: `docs/design/collections-hld.md`,
`docs/design/collections-lld.md`, diagrams in `docs/architecture/diagrams/`.

## 5. Evaluation results

Produced by `make eval` (`LLM_MODE=replay`, 2026-10-02), copied from `docs/evals/report.md`:

| Set | Result |
| --- | --- |
| Reply classification (40 labelled replies) | 39/40 (98%) |
| Amount extraction | 39/40 (98%) |
| Date extraction | 39/40 (98%) |
| Expected action | 31/40 (78%), mostly label naming (`human_review` for `escalate`); see the report |
| Red-team drafts rejected with the expected code | 23/23 |
| Golden drafts passing every check | 6/6 |
| Trajectory scenarios | 12/12 |

These replay-mode numbers come from the deterministic classifier (no fixtures recorded yet); record fixtures
with `LLM_MODE=record` and a key to measure the model itself.

## 6. Environment variables

| Variable | Default | Read by | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://collections:collections@postgres:5432/collections` | all | |
| `OPENROUTER_API_KEY` | empty | gateway | secret; only for live and record |
| `LLM_MODEL` | `anthropic/claude-haiku-4.5` | gateway | ADR-0007 |
| `LLM_MODE` | `replay` | gateway | live, replay, record |
| `LLM_BUDGET_USD` | `2.00` | seeds settings | runtime value in the settings row |
| `LLM_MAX_TOKENS` | `500` | gateway | capped at 500 |
| `LLM_TIMEOUT_S` | `20` | gateway | |
| `SMTP_HOST` / `SMTP_PORT` | `mailhog` / `1025` | email channel | |
| `EMAIL_ALLOW_REAL` | empty | email channel | comma-separated addresses mailed for real even when `EMAIL_REDIRECT_TO` redirects everything else; only your own test inboxes (HACK-007) |
| `MAILHOG_UI_URL` | `http://localhost:8025` | links | |
| `DEMO_TODAY` | `2026-09-30` | seeds settings | runtime value in the settings row |
| `TZ` | `Asia/Kolkata` | all | |
| `SENDING_ENABLED` | `true` | seeds settings | the kill switch at runtime |
| `AUTONOMY_MODE` | `manual` | seeds settings | manual, assisted, trusted |
| `ADMIN_TOKEN` | empty | api | secret; access code for the admin role (Bearer token); empty disables the role (ADR-0013) |
| `COLLECTOR_TOKEN` | empty | api | secret; access code for the collector role |
| `VIEWER_TOKEN` | empty | api | secret; access code for the viewer role |
| `DEMO_OPEN_ROLES` | `false` (compose: `true`) | api | `true` lets the role picker sign in with no code; your own machine only. The API refuses to start with it on when `ALLOWED_HOSTS` names a public host |
| `FEATURE_WHATSAPP` / `FEATURE_VOICE` / `FEATURE_PAYMENT_LINK` / `FEATURE_TRUSTED_MODE` / `FEATURE_SMS` | `false` | seeds settings | |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | empty | api, worker | secret (token); empty means SIMULATED SMS, WhatsApp and voice |
| `TWILIO_FROM_NUMBER` / `TWILIO_WHATSAPP_FROM` | empty | api, worker | E.164 sender numbers |
| `VOICE_PUBLIC_BASE_URL` | empty | api | public https URL Twilio calls back; webhook signatures are checked against it |
| `LLM_PROVIDER` | `openrouter` | gateway | `ollama` for a free local open-source model (no key, zero cost) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | gateway | where Ollama listens |
| `SMS_GATEWAY_URL` / `SMS_GATEWAY_USER` / `SMS_GATEWAY_PASSWORD` | empty | worker | free SMS through the open-source Android SMS Gateway app; password is a secret |
| `BANK_WEBHOOK_SECRET` | empty | api | secret; when empty the api uses a random one per process, so only the admin simulator can post credits |
| `MCP_TOKEN` | empty | mcp | secret; required for the HTTP transport |
| `SESSION_SECRET` | empty | api | reserved for payment-link tokens |
| `CLASSIFY_MIN_CONFIDENCE` | `0.75` | reply role | below it a reply goes to a human |
| `LOG_LEVEL` | `INFO` | all | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,api,testserver` | api | Host headers answered; others get 400 (DNS rebinding) |

Demo roles (Admin, Collector, Viewer) are chosen on the sign-in screen; there are no passwords because the
stack binds to localhost only.
