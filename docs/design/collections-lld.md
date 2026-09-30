# Low Level Design: AI Receivables Collections Agent

- Task: HACK-001
- Author, date: Savitha Sista with Claude Code, 2026-09-30
- Status: Draft
- HLD: docs/design/collections-hld.md (Reviewed); data model: docs/design/data-model.md, docs/design/schema.sql; API: api/openapi.yaml; threats: docs/security/threat-model-collections-agent.md
- Serves: REQ-001 to REQ-120; US-00-001 to US-03-004; ADR-0001 to ADR-0011

## 1. Scope

The whole backend (api, mcp, worker entrypoints over one package), the web console's structure, the evaluation harness and the compose setup. This one LLD also carries the lightweight Phase 4 designs the master prompt names: auth (section 8.1), background jobs (8.2), webhooks (8.3), feature patterns (8.4). Out of scope: visual design (Phase 5), prompt wording (Phase 6 `prompt-registry`).

## 2. Module layout

```
backend/
  pyproject.toml, uv.lock, Dockerfile, alembic.ini
  migrations/versions/0001_initial_schema.py   applies docs/design/schema.sql (copied to backend/app/db/schema.sql)
  app/
    core/        config.py (pydantic-settings), db.py (engine, session, transaction helper), clock.py,
                 money.py (paise <-> INR text, Indian number parser), errors.py (ErrorCode, AppError),
                 logging.py (JSON logs, request id, run id), security.py (password hash, HMAC)
    models/      SQLAlchemy mapped classes, one module per table group
    services/    the only writers (tenet 3): ledger.py, priority.py, tone.py, drafting.py, approval.py,
                 sending.py (send_gate, claim, deliver), replies.py, promises.py, disputes.py,
                 escalations.py, payments.py, timeline.py, settings.py, demo.py (seed, reset), auth.py,
                 evals.py, idempotency.py
    guardrails/  extract.py (invoice, amount, date, name tokens), verify.py (draft checks + report),
                 tone.py (lexicon from policy/guardrails.yaml), injection.py, events.py
    channels/    base.py (MessageChannel protocol), email.py, whatsapp.py (simulated), voice.py (prep only)
    llm/         gateway.py, pricing.py, replay.py, prompts.py (loads prompts/<name>/vN.md)
    tools/       schemas.py (Pydantic in/out per tool), registry.py (ToolRegistry, budget wrapper,
                 error envelope), impl.py (13 tool functions calling services)
    agent/       orchestrator.py, roles/collections.py, roles/reply.py, roles/payment.py, roles/escalation.py
    api/         main.py (app factory, error handlers, request id), deps.py (session, roles),
                 routers/ one per OpenAPI tag
    mcp/         __main__.py (MCPServer over the registry; --stdio or HTTP)
    worker/      __main__.py (poll loop), jobs.py (handlers), scheduler.py (09:00 IST enqueue), reaper.py
    seed/        generator.py (fixed RNG), abc_story.py (ABC Distributors fixture), replies.py (40 labelled)
  tests/         unit/, service/, tool/, api/, e2e/, vectors/inr.json (shared with web)
prompts/         draft_reminder/v1.md, classify_reply/v1.md, call_prep/v1.md (Phase 6)
policy/          guardrails.yaml (tone lexicon, legal allow-list, trusted allow-list rules)
evals/           replies.jsonl (40 labelled), scenarios/*.yaml (>= 10), redteam/*.yaml, golden/*.yaml,
                 fixtures/<prompt>/<key>.json (replay), fixtures/manifest.json, run.py
web/             Vite + React app: src/api (generated client), src/lib/format.ts (INR, dates),
                 src/routes (Today, Approvals, Customers, Customer, Evaluation, Admin, Pay), src/components
compose.yaml, .env.example, Makefile
```

Ownership: one team; `services/` owns every table (data model section 2 names the service per table).

## 3. Types and schemas

### 3.1 Money

- Storage and API: integer paise (`int`, `BIGINT`). No floats anywhere.
- `money.format_inr(paise) -> str`: `₹` + Indian grouping of rupees (last three digits, then pairs) + `.pp` only when paise ≠ 0. `75_000_000 → "₹7,50,000"`; `1_500_000 → "₹15,000"`; `250_000_000 → "₹25,00,000"`; `12_345 → "₹123.45"`.
- `money.parse_amounts(text) -> list[AmountSpan(start, end, paise, raw)]`, the Indian number parser:
  - token regex (case-insensitive): `(?P<cur>₹|rs\.?|inr)?\s*(?P<num>\d{1,3}(?:,\d{2})*(?:,\d{3})|\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d{1,2}))?\s*(?P<unit>crores?|cr|lakhs?|lacs?|l|k|thousand)?(?:\s*/-)?`
  - a match is an amount only when it has a currency prefix, a unit, comma grouping, or `/-`; bare integers are not amounts (they are dates, counts or invoice digits). Tokens inside `INV-\d+` or inside a matched date are skipped.
  - value: `Decimal(num without commas + "." + dec) × unit` with lakh = 10^5, crore = 10^7, k/thousand = 10^3; paise = value × 100, which must be an integer (else the span is flagged `AMOUNT_UNPARSEABLE`).
  - vectors (tests/vectors/inr.json): `₹4,00,000`, `Rs 4 lakh`, `4L`, `Rs. 4,00,000/-`, `4.0 lakhs`, `INR 400000` all give 40,000,000; `₹3 cr` gives 3,000,000,000; `400000` alone gives nothing.

### 3.1b Dates from replies (REQ-065, REQ-066)

The classifier returns `date_text` exactly as written; `clock.resolve_date(text, today, direction)` decides the date, where direction is `future` for PROMISE and `past` for PART_PAYMENT and PAYMENT_CONFIRMATION. Rules, pinned by `evals/replies.jsonl` with today = Wed 30 Sep 2026:

| Text | Rule | Result |
| --- | --- | --- |
| `October 5`, `5 Oct`, `15 October 2026`, `12 October` | explicit day and month; year = the next (future) or last (past) occurrence | 2026-10-05, 2026-10-15, 2026-10-12 |
| `7/10/2026`, `25/09/2026` | day first | 2026-10-07, 2026-09-25 |
| `5th`, `3rd Oct`, `on 20th` | day only: next such day (future) or most recent (past) | 2026-10-05; past `20th` = 2026-09-20 |
| `tomorrow`, `today`, `yesterday`, `yday` | offset from today | 2026-10-01, 2026-09-30, 2026-09-29 |
| `next Friday`, `Monday` | the first such weekday after today | 2026-10-02, 2026-10-05 |
| `10 days` (in "give 10 days") | today + N days | 2026-10-10 |
| `last week`, `end of Oct`, `soon`, `next month` | not a single date | null (no date; a promise without a date needs review) |

Impossible dates (`31 Sep`) raise DATE_INVALID. Amounts come from `amount_text` through `money.parse_amounts` (3.1); a reply amount must be inside the text the customer wrote, or it is dropped (AC-US-00-012-3). Prompt loader rule: only declared front-matter variables are substituted; other `{{...}}` text (the drafting placeholders) passes through unchanged.

### 3.2 Priority formula (REQ-026 to REQ-028)

Inputs per customer from the ledger on `clock.today()`, excluding invoices with an open dispute from the overdue figures: `overdue_paise`, `oldest_days` (max days overdue), `overdue_count`, `missed_promises` (status missed, any time), `open_disputes`, `segment`.

| Factor | Normalisation | Weight | Reason code (when it fires) and text |
| --- | --- | --- | --- |
| amount overdue | min(overdue_paise / 50,000,000, 1) (₹5,00,000 caps) | 35 | `HIGH_OUTSTANDING` if overdue ≥ ₹2,00,000: "High outstanding (₹7,50,000)" |
| oldest days overdue | min(oldest_days / 60, 1) | 20 | `OLDEST_OVERDUE` if > 0: "Oldest invoice 19 days overdue" |
| missed promises | min(missed / 2, 1) | 20 | `MISSED_PROMISES` if ≥ 1: "1 missed promise" |
| overdue invoice count | min(count / 4, 1) | 10 | `MANY_OVERDUE` if ≥ 3: "3 overdue invoices" |
| segment | enterprise 1.0, mid_market 0.7, sme 0.4 | 10 | `KEY_ACCOUNT` if enterprise: "Key account" |
| open dispute | −5 per open dispute, floor 0 | n/a | `OPEN_DISPUTE`: "Open dispute on INV-1047 (excluded)" |

Score = round(sum of weight × factor) − 5 × open_disputes, clamped 0 to 100 (weights sum to 95; 5 points of headroom keep 100 unreachable without every factor maxed). Bands: HIGH ≥ 60, MEDIUM 35 to 59, LOW < 35 (Q-002, revised from 70/40). Tie-break: overdue_paise desc, then customer name. A customer with overdue_paise = 0 is never selected. Top 15 by score.

Worked example, ABC Distributors on 30 Sep 2026: amount 1.0 × 35 = 35; days 19/60 × 20 = 6.33; missed 1/2 × 20 = 10; count 3/4 × 10 = 7.5; mid_market 0.7 × 10 = 7; total 65.83 → 66, HIGH, reasons HIGH_OUTSTANDING, OLDEST_OVERDUE, MISSED_PROMISES, MANY_OVERDUE. Unit tests pin this and one fixture per factor (AC-US-00-002-1 to AC-US-00-002-4).

### 3.3 Tone (REQ-031)

`final` if (missed ≥ 1 and oldest_days > 30) or missed ≥ 2 or oldest_days > 90; else `firm` if oldest_days > 14 or missed ≥ 1 or a reminder was sent in the last 14 days; else `gentle`. ABC: missed 1, 19 days → firm. Fixtures from AC-US-01-001-3: first reminder, 5 days → gentle; 20 days → firm; missed 1 + 45 days → final.

### 3.4 Channel

`email` unless `settings.feature_whatsapp` and the customer has sent a WhatsApp reply before (a seed flag); voice is never chosen by the agent (call prep is a collector action).

### 3.5 MCP tool specs

All tools: input model with `extra="forbid"`; output envelope `{ok: true, data: <Out>}` or `{ok: false, error: {code, message, details?}}`. A field named `sql`, `query` or `raw` in any input is refused with `VALIDATION_ERROR` and a GuardrailEvent `DIRECT_DB_ATTEMPT` (REQ-042). MCP and orchestrator calls go through `ToolRegistry.invoke(name, args, ctx)`; `ctx` carries actor (`ai`, source `mcp` or `agent`), role, run id and the call budget.

| Tool | Input | Output | Errors | Side effects | Idempotency |
| --- | --- | --- | --- | --- | --- |
| `list_overdue` | `limit: int 1..50 = 15` | `[{customer_id, name, score, band, reasons[], overdue_paise}]` | VALIDATION_ERROR | none | read |
| `get_customer_history` | `customer_id: uuid` | `{customer, invoices[], promises[], disputes[], last_messages[] (subject, status, sent_at), reply_summaries[] (class, date)}`; no reply bodies (T-18) | NOT_FOUND | none | read |
| `get_invoice` | `invoice_number: str ^INV-\d+$` | invoice with balances | NOT_FOUND | none | read |
| `get_customer` | `customer_id` | customer with outstanding | NOT_FOUND | none | read |
| `draft_message` | `customer_id, kind (reminder, followup, statement, dispute_ack), prose: str (must contain {{invoice_table}} and {{total}} for reminder, followup, statement), invoice_numbers?: [str]` | `{message_id, status, guardrail_report[]}` | PLACEHOLDER_MISSING, guardrail codes, INVOICE_DISPUTED, NOT_FOUND | message (pending_approval or rejected), message_invoices, timeline, guardrail events | one open draft per customer and kind: a second call replaces the text of the pending one (version + 1) |
| `send_message` | `message_id` | `{message_id, status, job_id}` | NOT_APPROVED, NOT_VERIFIED, SENDING_DISABLED, FEATURE_DISABLED, INVOICE_DISPUTED | enqueues send job | job key = message id |
| `log_promise` | `customer_id, amount_paise > 0, promised_date, invoice_numbers?, reply_id?` | promise | VALIDATION_ERROR, NOT_FOUND | promise, promise_invoices, timeline | one pending promise per reply |
| `log_dispute` | `customer_id, invoice_number, reason (<= 200 chars), reply_id?` | dispute | NOT_FOUND, INVOICE_WRONG_CUSTOMER, DISPUTE_EXISTS | dispute, invoice status disputed, timeline | unique open dispute per invoice |
| `escalate` | `customer_id, kind, reason, dispute_id?, reply_id?, payment_id?` | escalation | VALIDATION_ERROR | escalation, timeline | one open escalation per (kind, source id) |
| `record_payment` | `customer_id, amount_paise, received_on, reference, ledger_evidence: {bank_event_id} ` | payment | NO_LEDGER_EVIDENCE (no stored bank event), VALIDATION_ERROR | none beyond matching an existing feed payment | idempotent on bank_event_id |
| `check_promise_status` | `promise_id` | promise with matched payments | NOT_FOUND | may settle a promise (same code as the promise check) | idempotent |
| `create_followup` | `customer_id, reason` | `{message_id}` via drafting with kind followup | as draft_message | as draft_message | as draft_message |
| `classify_reply` | `reply_id` | classification | NOT_FOUND, CLASS_INVALID, BUDGET_EXHAUSTED | reply classification fields | re-running overwrites with the same replayed result |

Roles' allow-lists: Collections: list_overdue, get_customer_history, get_invoice, check_promise_status, draft_message, escalate. Reply Understanding and Payment Verification: no model-driven tools (code maps class to sequence, HLD Flow B). Escalation: escalate. MCP clients: all 13 as collector (no admin tools exist).

## 4. Sequence

HLD section 2 carries the three flows. The orchestrator loop for the Collections role:

```
run = start_run(customer, trigger)            # unique running run per customer
ctx.tone, ctx.channel = tone(), channel()     # code, before any model call
msgs = [system(prompt draft_reminder vN), user(customer facts as JSON, tone, channel)]
loop:
    r = gateway.complete(msgs, tools=allow_list(COLLECTIONS), max_tokens=500)
    if r.final: break
    if ctx.calls == 4: record STOPPED_LIMIT (GuardrailEvent TOOL_LIMIT); break   # 5th not executed
    out = registry.invoke(r.tool, r.args, ctx)   # ctx.calls += 1; step row written
    msgs += [assistant(r), tool_result(out)]
finish_run(outcome = WAIT_FOR_APPROVAL if a pending draft exists
                     else ESCALATED if an escalation was created else NO_ACTION)
```

A model turn that returns a tool outside the allow-list is answered with a tool error `TOOL_NOT_ALLOWED` and counts as a call.

## 5. Data access

- DDL: docs/design/schema.sql (21 tables, 40 indexes, 53 named checks, view `invoice_balances`); migration 0001 applies it.
- State machines (enforced in services; CHECKs hold the value sets):

```
Invoice:   unpaid --allocation partial--> partially_paid --allocation rest--> paid
           unpaid|partially_paid --log_dispute--> disputed --resolve--> (unpaid|partially_paid|paid by balance)
Message:   draft --verify ok--> pending_approval --approve--> approved --send ok--> sent
           draft --verify fail--> rejected (reason = guardrail code)
           pending_approval --edit--> pending_approval (version+1, re-verified; fail stays pending with the error, text not saved)
           pending_approval --reject--> rejected
           approved --send error x5 | unconfirmed--> failed --manual resend--> approved
Promise:   pending --payments cover by date--> fulfilled
           pending --date passed, partial--> partially_fulfilled
           pending --date passed, none--> missed
Dispute:   open --resolve--> resolved
Escalation: open --resolve--> resolved
AgentRun:  running --finish--> finished (outcome WAIT_FOR_APPROVAL | ESCALATED | STOPPED_LIMIT | NO_ACTION | FAILED)
```

- Queries that matter: outstanding and overdue per customer from `invoice_balances` joined to `invoices` (open-invoice partial index); priority inputs in one grouped query; dashboard in one query per panel; approval queue by `idx_messages_status_created_at`; job poll `SELECT ... WHERE status='queued' AND run_at <= now() ORDER BY run_at FOR UPDATE SKIP LOCKED LIMIT 1`.
- Allocation: payment with a referenced invoice number (regex on `reference`) goes to that invoice first, capped at its remaining; the rest goes oldest due date first across the customer's non-disputed open invoices; any excess stays unallocated and raises an escalation `payment_needs_verification`. Then statuses are recomputed from `invoice_balances`, and the customer's pending promises are re-evaluated (HLD Flow C), all in one transaction.
- Promise evaluation: matched payments for the customer with `received_on` between the promise's creation business date and `promised_date`, summed; ≥ amount → fulfilled (immediately, on payment); after the date passes: some → partially_fulfilled, none → missed.
- Reset (`services/demo.py`): `TRUNCATE` all tables except users, sessions, llm_calls (and alembic_version), reseed, set `settings` from env, set the clock to `DEMO_TODAY`.

## 6. Errors

One `ErrorCode` enum (UPPER_SNAKE), one envelope: `{"error": {"code", "message", "details", "request_id"}}` over HTTP (api/openapi.yaml `Error`), `{"ok": false, "error": {...}}` over tools.

| Code | HTTP | Raised by |
| --- | --- | --- |
| VALIDATION_ERROR | 422 | request or tool schema |
| UNAUTHORIZED / FORBIDDEN / NOT_FOUND | 401 / 403 / 404 | auth, role matrix, lookups |
| STALE_DRAFT | 409 | edit or approve with an old If-Match version |
| NOT_APPROVED, NOT_VERIFIED, SENDING_DISABLED, FEATURE_DISABLED, INVOICE_DISPUTED | 409 | send gate |
| AMOUNT_MISMATCH, INVENTED_AMOUNT, TOTAL_MISMATCH, INVOICE_NOT_FOUND, INVOICE_WRONG_CUSTOMER, CUSTOMER_MISMATCH, DATE_INVALID, DATE_MISMATCH, TONE_UNSAFE, PLACEHOLDER_MISSING, AMOUNT_UNPARSEABLE | 422 | guardrails |
| REASON_REQUIRED, MESSAGE_CUSTOMER_MISMATCH, DISPUTE_EXISTS, NO_LEDGER_EVIDENCE, CLASS_INVALID, IDEMPOTENCY_MISMATCH | 422 / 409 | services |
| SIGNATURE_INVALID, REPLAY_WINDOW | 401 | webhook |
| BUDGET_EXHAUSTED, LLM_UPSTREAM, LLM_TIMEOUT, REPLAY_MISS | 503 (api) / tool error | gateway |
| TOOL_LIMIT, TOOL_NOT_ALLOWED, DIRECT_DB_ATTEMPT, PROMPT_INJECTION_SUSPECTED | tool error | registry, injection check |
| RATE_LIMITED | 429 | sign-in |
| INTERNAL | 500 | unmapped exception (logged with request id) |

### 6.1 Guardrail algorithms (brief section 7; each writes a GuardrailEvent on failure)

Draft verification (`guardrails/verify.py`) on the final text, with the customer, the cited invoices (`message_invoices`) and the ledger:

1. Placeholders: any `{{...}}` left → PLACEHOLDER_MISSING.
2. Invoice numbers: `\bINV-\d+\b`. Unknown → INVOICE_NOT_FOUND; owned by another customer → INVOICE_WRONG_CUSTOMER; open dispute and kind ≠ dispute_ack → INVOICE_DISPUTED.
3. Amounts: `parse_amounts`. On a line that names exactly one invoice, the amount must equal that invoice's remaining (or original) amount → else AMOUNT_MISMATCH. On a line with "total" (case-insensitive), it must equal the sum of remaining over cited invoices → else TOTAL_MISMATCH. Any other amount must be in the allowed set {each cited remaining, each cited amount, the total, the pending promise amount} → else INVENTED_AMOUNT.
4. Dates: `\d{1,2} (Jan|...|Dec)[a-z]* \d{4}`, `\d{1,2}/\d{1,2}/\d{4}` (day first), ISO, and "Month day". Not a real calendar date → DATE_INVALID. On an invoice line it must equal that invoice's due date → DATE_MISMATCH. Elsewhere: a past date must be a cited due date or a promise date; a future date must be within 60 days of today.
5. Customer name: a salutation (`Dear|Hello|Hi|To`) followed by a name must match the customer's name (case- and punctuation-insensitive) → else CUSTOMER_MISMATCH; any other seeded customer's name appearing anywhere → CUSTOMER_MISMATCH.
6. Tone: `policy/guardrails.yaml` categories (threat, abuse, harassment, legal, third_party, shaming, false_urgency, unlisted_consequence), each a list of case-insensitive regexes; a hit → TONE_UNSAFE with the category; the `legal_allow` list (empty by default) exempts exact phrases.
7. The report lists every token checked with ok or its code (AC-US-00-009-5); any failure rejects the draft.

Other guardrails: send without approval or with a stale verification (send gate, 3 paths); send while the kill switch is on (send gate); edited draft not re-verified (`chk_messages_approved_verified` plus approve check); tool call beyond limit (registry wrapper); direct DB attempt (input field names); payment marked on a claim (only `payments.allocate` changes paid amounts and it requires a stored payment row); prompt injection (`guardrails/injection.py`: regexes such as `ignore (all|previous) instructions`, `system prompt`, `you are now`, `mark .* (paid|settled)`, `disregard`; a hit sets needs_review, forces escalation, logs PROMPT_INJECTION_SUSPECTED, and classification still runs with no tools); LLM over budget (gateway reservation).

## 7. Configuration

| Variable | Default | Read by | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://collections:collections@postgres:5432/collections` | all | |
| `OPENROUTER_API_KEY` | empty | gateway | secret; only needed for live and record |
| `LLM_MODEL` | `anthropic/claude-haiku-4.5` | gateway | ADR-0007 |
| `LLM_MODE` | `replay` | gateway | live, replay, record |
| `LLM_BUDGET_USD` | `2.00` | seeds settings | runtime value in `settings` |
| `LLM_MAX_TOKENS` | `500` | gateway | capped at 500 |
| `LLM_TIMEOUT_S` | `20` | gateway | |
| `SMTP_HOST` / `SMTP_PORT` | `mailhog` / `1025` | email channel | |
| `MAILHOG_UI_URL` | `http://localhost:8025` | web links, e2e | Mailpit API at `/api/v1/messages` |
| `DEMO_TODAY` | `2026-09-30` | seeds settings | runtime value in `settings` |
| `TZ` | `Asia/Kolkata` | all | business day boundaries |
| `SENDING_ENABLED` | `true` | seeds settings | kill switch at runtime |
| `AUTONOMY_MODE` | `manual` | seeds settings | |
| `ADMIN_TOKEN` | empty | api | secret; scripts |
| `FEATURE_WHATSAPP` / `FEATURE_VOICE` / `FEATURE_PAYMENT_LINK` / `FEATURE_TRUSTED_MODE` | `false` | seed settings | |
| `BANK_WEBHOOK_SECRET` | empty (required) | api | secret |
| `MCP_TOKEN` | empty (required for HTTP) | mcp | secret |
| `SESSION_SECRET` | empty (required) | api | secret; also signs payment-link tokens |
| `CLASSIFY_MIN_CONFIDENCE` | `0.75` | reply role | Q-001 |
| `LOG_LEVEL` | `INFO` | all | |

### 7.1 Gateway

`complete(prompt: PromptRef(name, version), messages, tools=None, max_tokens=500) -> LlmResult(text | tool_call, usage, cost_micro_usd, replay_key)`.
- Pricing table (micro-USD per token): `anthropic/claude-haiku-4.5`: input 1, output 5 (spike 2026-09-30).
- Budget: inside `pg_advisory_xact_lock(4242)`, `spent = sum(cost_micro_usd)` over `llm_calls`; reserve `max_tokens × out + estimated_input × in`; refuse with BUDGET_EXHAUSTED if `spent + reserve > settings.llm_budget_micro_usd`; insert the call row with the reserved cost; commit; call; update the row with the actual cost. Replay calls cost 0.
- Retries: 429, 5xx and connect errors, 3 tries, delays 1 s, 2 s, 4 s with jitter; timeout `LLM_TIMEOUT_S`; then LLM_UPSTREAM or LLM_TIMEOUT.
- Replay key: `f"{name}@v{version}:" + sha256(canonical_json({model, messages, tools, max_tokens}))[:24]`; fixtures at `evals/fixtures/<name>/<key>.json`; `manifest.json` stores the seed hash and prompt versions; a mismatch fails with "fixtures recorded for seed X, prompts Y". Record mode writes fixtures after live calls. Replay with no fixture: REPLAY_MISS naming the key.

### 7.2 Channels

```python
class MessageChannel(Protocol):
    name: str
    def send(self, message: OutboundMessage) -> SendResult: ...   # raises ChannelError(code, retryable)
```
`EmailChannel`: `smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)`, `Message-ID: <{message_id}@collections.local>`, From `collections@demo-business.example.in`, To the customer's stored email only. `WhatsAppChannel`: simulated, records provider id `sim-wa-<uuid>` and returns; provider-pluggable by class. `VoiceChannel`: `send` raises `ChannelError("VOICE_PREP_ONLY", retryable=False)`; `prepare(customer) -> CallPrep`.

## 8. Cross-cutting designs

### 8.1 Auth (lightweight `auth`)

Sessions: sign-in checks argon2 hash, creates a 32-byte random cookie `ca_session` (HttpOnly, SameSite=Lax, 12 h), stores its SHA-256 in `sessions`. `ADMIN_TOKEN` bearer acts as admin for scripts. CSRF: unsafe methods require `Origin` equal to the web origin (T-02). Sign-in rate limit: 5 failures per email per minute (in-memory in the single api process; ponytail: move to Postgres if api ever runs more than one replica).

| Operation group | viewer | collector | admin |
| --- | --- | --- | --- |
| read dashboard, customers, timeline, runs, messages, replies, promises, disputes, escalations, payments, evals | yes | yes | yes |
| edit, approve, reject, resend, approve-batch, simulate reply, check payment, resolve dispute or escalation, match payment | no | yes | yes |
| start run, settings, clock, reset, simulate bank credit, guardrail events, run list | no | no | yes |
| MCP tools | n/a | all 13 (acts as collector) | n/a |

A parametrised test calls every operation in `api/openapi.yaml` (`x-roles`) and every tool as each role.

### 8.2 Background jobs (lightweight `background-jobs`)

| Job | Enqueued by | Dedupe key | Handler | Retries | On final failure |
| --- | --- | --- | --- | --- | --- |
| `daily_run` | scheduler at 09:00 IST on the demo date; `POST /runs` | `run_date` | top 15 by priority, one Collections run each, sequentially | 1 retry | dead; admin shows it |
| `promise_check` | clock advance; scheduler daily | business date | settle promises with date < today | 3 | dead |
| `send_message` | approve (and Trusted auto-send) | message id | claim: attempts+1, last_error IN_FLIGHT, commit; send gate again; channel.send; mark sent (timeline) or record the error code | 5 attempts (first plus 4 retries), backoff 10 s × 2^n | message failed, timeline send_failed |

Poll: every 2 s, one job at a time. Reaper every 60 s: a `running` job locked over 5 minutes is requeued, except `send_message` whose message shows IN_FLIGHT: that message becomes failed with UNCONFIRMED and the job dead (at most once, HLD section 7). Graceful shutdown: finish the current job, then exit on SIGTERM.

### 8.3 Webhooks (lightweight `webhooks`)

Inbound only. `POST /webhooks/bank`: headers `X-Bank-Timestamp` (unix seconds) and `X-Bank-Signature` = hex HMAC-SHA256 of `"<timestamp>.<raw body>"` with `BANK_WEBHOOK_SECRET`; `hmac.compare_digest`; |now − timestamp| ≤ 300 s else REPLAY_WINDOW; body validated; `event_id` unique (duplicate → 200 with the existing payment). Stored `received_on = clock.today()`. The admin simulate endpoint builds the same body, signs it in-process and calls the same handler function. No outbound webhooks.

### 8.4 Feature patterns (lightweight `feature-patterns`)

- Payments: ledger-only truth; idempotency by bank event id and `idempotency_keys`; allocation rules in section 5; failure modes in HLD section 7.
- Notifications: the send queue in 8.2; email and simulated WhatsApp behind one interface; no push or in-app notifications.
- Rate limiting: sign-in only (8.1); the LLM budget is the cost limiter.
- Caching: none; data is small (HLD section 8).
- Realtime: none; the console refetches with TanStack Query on focus and every 10 s on the approvals and admin pages.

## 9. Tests

| Layer | Tool | What | Count target |
| --- | --- | --- | --- |
| unit | pytest | money parser and formatter (shared vectors), priority, tone, extract, verify, tone lexicon, injection, replay key, pricing | one per rule plus the vectors |
| service | pytest + Postgres | every state change writes timeline; allocation; promise evaluation; send claim and reaper; kill switch; reset keeps llm_calls; status consistency with the view | one per AC that touches the database |
| tool | pytest + MCP client | each of 13 tools over stdio and HTTP (spike harness), schema rejection, DIRECT_DB_ATTEMPT | 13 × 2 |
| api | pytest + httpx | role matrix over every operation; webhook signature, window, duplicate; idempotency keys; error envelope | per operation |
| eval | `make eval` (replay) | 40 replies, ≥ 10 scenarios, red-team and golden sets | as REQ-101 to REQ-103 |
| e2e | pytest (API, replay) | the ABC story, every beat of REQ-110 | 1 |
| ui | Playwright + axe | story smoke, accessibility | 1 + scan |
| web unit | vitest | format.ts against tests/vectors/inr.json | vectors |

TC ids are assigned by `test-cases` in Phase 8 per AC.

## 10. Work breakdown (MR-sized, in build order; ADR-0011 puts the payment beats in P0)

| # | Change | Stories | Size |
| --- | --- | --- | --- |
| 1 | Repo scaffold, compose, Makefile, CI, hooks (`new-repo`, Phase 7) | US-01-013 | M |
| 2 | Schema migration, models, clock, money, errors, logging | US-00-001, US-00-023 | M |
| 3 | Seed generator with the ABC fixture and 40 replies; reset | US-01-003, US-01-005 | M |
| 4 | Ledger read APIs, priority and tone | US-00-001, US-00-002 | M |
| 5 | Gateway (replay first), pricing, budget | US-01-008, US-01-009 | M |
| 6 | Tool registry, 7 core tools, MCP server both transports | US-03-002 | L |
| 7 | Guardrails and drafting with placeholders | US-00-005, US-00-006, US-00-007 | L |
| 8 | Orchestrator, Collections role, runs and steps, jobs and scheduler | US-01-001, US-00-008 | L |
| 9 | Approval queue API, edit and re-verify, send gate, email channel, send worker | US-00-009, US-00-010, US-00-011 | L |
| 10 | Replies: ingest, classify, injection, promise, dispute, escalations | US-03-001, US-00-012 to US-00-016 | L |
| 11 | Payments: webhook, matching, allocation, promise evaluation, clock advance | US-00-017, US-00-019, US-00-020, US-01-004 | L |
| 12 | Timeline API, dashboard, customer page API | US-00-022, US-00-003, US-00-004 | M |
| 13 | Web console (P0 screens) | US-00-003, US-00-004, US-00-009, US-00-022, US-00-023 | L |
| 14 | Evals harness, labelled set, scenarios, red-team, report and page | US-01-010, US-01-011, US-01-012 | L |
| 15 | E2E story test, README | US-01-005, US-01-015 | M |
| 16 | P1: kill switch, admin, roles, health and logs, claims, today's promises, statements, extra tools | US-01-002, US-01-006, US-01-007, US-01-014, US-00-018, US-00-021, US-00-015, US-03-003 | L |
| 17 | P2 behind flags | US-00-024 to US-00-026, US-03-004, US-01-016 | L |

## 11. Assumptions

- assumption: OpenRouter's OpenAI-compatible tool calling works for `anthropic/claude-haiku-4.5` with `tools` and `tool_choice: auto`; verify in step 5 with one recorded call.
- assumption: argon2 via `argon2-cffi`; if the wheel cannot be installed on the slow network, `hashlib.scrypt` from the standard library is the fallback.
- The 16 PRD assumptions in docs/product/questions.md stand until the engineer answers them.
