# Data model: AI Receivables Collections Agent

**Store:** PostgreSQL · **Tables:** 21 · **Columns:** 186 · **Indexes:** 40 · **Personal-data columns:** 8

One PostgreSQL 17 database holds the ledger (customers, invoices, payments, allocations), the collections workflow (messages, replies, promises, disputes, escalations), the audit trail (timeline events, agent runs and steps, guardrail events, LLM calls) and runtime state (settings, jobs, users, sessions). The api, mcp and worker processes read and write it only through the service layer (tenet 3); the web console reaches it only through the api. One relational store is enough: every query is a join over a few hundred rows, the job queue fits in a table (ADR-0006), and the audit trail must commit in the same transaction as the change it records.

- Task: HACK-001
- Serves: US-00-001 to US-00-026, US-01-001 to US-01-016, US-03-001 to US-03-004; REQ-002, REQ-005 to REQ-017, REQ-022, REQ-026 to REQ-036, REQ-062 to REQ-081, REQ-095, REQ-096, REQ-099 to REQ-111
- ADRs: ADR-0003 (store), ADR-0006 (job table), ADR-0009 (sessions)
- Stores: postgres
- Companion files: `docs/design/schema.sql`, `docs/design/data-dictionary.csv`, `docs/design/erd.md` (all generated from one spec; see section 9)
- Author: Savitha Sista, 2026-09-30, status Reviewed, version v1

## 1. Why these stores

### PostgreSQL

Holds everything. Money is BIGINT paise (REQ-002), statuses are CHECK-constrained text (brief section 6), balances come from the `invoice_balances` view (REQ-008), and the job queue uses `SELECT ... FOR UPDATE SKIP LOCKED` (ADR-0006).

| Considered | Why not |
| --- | --- |
| Redis for jobs and sessions | a second service; the timeline and job enqueue must commit atomically with the ledger change (tenet 3) |
| A document store for trajectories | trajectories are small, joined to runs and customers, and read in order; jsonb columns cover the arguments |
| A separate analytics store | the dashboard aggregates a few hundred rows (HLD section 11) |

## 2. Entities: ownership and lifecycle

| Entity | Owner (service) | Created by | Changed by | Ended by | Serves | PII | Retention |
| --- | --- | --- | --- | --- | --- | --- | --- |
| users | auth | seed | none | reset keeps them | US-01-007 | yes | UNDEFINED |
| sessions | auth | sign-in | none | sign-out, expiry | US-01-007 | no | expiry |
| settings | admin | migration | admin actions, reset | never | US-01-002, US-01-004, US-01-006, US-01-016 | no | singleton |
| customers | ledger | seed | none | reset | US-00-001 | yes | UNDEFINED |
| invoices | ledger | seed | allocation and dispute services (status only) | reset | US-00-001, US-00-019 | no | UNDEFINED |
| payments | payments | webhook, payment link, manual entry | match on verification | reset | US-00-017 to US-00-019 | no | UNDEFINED |
| payment_allocations | payments | allocation service | none | payment delete (cascade), reset | US-00-019 | no | follows payment |
| agent_runs, agent_steps | orchestrator | daily run, reply, payment | run finish | reset | US-01-001, US-00-008 | no (arguments redacted) | UNDEFINED |
| messages, message_invoices | drafting and approval | draft_message tool, statement action | approve, edit, reject, send worker | reset | US-00-005 to US-00-011 | yes (subject, body) | UNDEFINED |
| replies | replies | simulate reply, seed | classification | reset | US-03-001, US-00-012 | yes (body) | UNDEFINED |
| promises, promise_invoices | promises | log_promise | promise check, payment transaction | reset | US-00-014, US-00-020 | no | UNDEFINED |
| disputes | disputes | log_dispute | resolve | reset | US-00-016 | no | UNDEFINED |
| escalations | escalations | escalate (tool and services) | resolve | reset | US-00-016, US-00-012, US-00-017, US-00-018 | no | UNDEFINED |
| guardrail_events | guardrails | every refusal | none | reset | US-00-006, US-01-006 | no | UNDEFINED |
| llm_calls | gateway | every model call | actual cost after the call | reset keeps them (budget) | US-01-009 | no | UNDEFINED |
| timeline_events | every service | every state change | none (append-only) | reset | US-00-022 | no | UNDEFINED |
| jobs | worker | scheduler, clock advance, approval | worker | reset | US-01-001, US-00-011 | no | UNDEFINED |
| idempotency_keys | api | creating POSTs | none | reset | US-03-001, US-01-005 | no | until reset |

Not modelled: channel outbox for simulated WhatsApp beyond `messages` (a message with channel `whatsapp` and status `sent` is the outbox, US-00-024); bank events that fail signature checks (nothing is stored, AC-US-00-017-3).

## 3. Relationships

See `docs/design/erd.md` for the diagram and one sentence per foreign key. Deletes: ledger parents are `RESTRICT` (a customer with invoices cannot vanish); dependent audit links are `SET NULL`; purely owned children (`agent_steps`, `payment_allocations`, link tables, `timeline_events`, `sessions`) `CASCADE`. Demo reset truncates in one statement, so no delete rule is exercised in normal use.

## 4. PostgreSQL tables

Tables in the order `schema.sql` creates them.

### `users`: Console users (hot: no)

A person who signs in to the console with one role.

Serves US-01-007, US-00-009. Expected volume: 3 seeded rows (10^0); one per demo user.

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | US-01-007 AC1: the session carries the user; approvals name the approver (AC-US-00-009-2). |
| `email` | `text` | No | UK |  | Sign-in name. **(personal data)** | US-01-007 AC1: each seeded user signs in. |
| `display_name` | `text` | No |  |  | Name shown as the actor on timeline events. **(personal data)** | AC-US-00-022-3: actor label for human actions. |
| `role` | `text` | No |  |  | admin, collector or viewer. | US-01-007 AC2: role matrix. |
| `password_hash` | `text` | No |  |  | Password hash (argon2 or bcrypt). | US-01-007 AC1: sign in with a password (Q-014). |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_users_email`: unique on (lower(email)). Serves sign-in lookup by email, case-insensitive (US-01-007 AC1).

**Constraints**

- `chk_users_role`: `role IN ('admin','collector','viewer')`. Refuses a role outside the matrix.

### `sessions`: Sign-in sessions (hot: no)

A server-side session for one signed-in user.

Serves US-01-007. Expected volume: tens of rows (10^1); one per sign-in.

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `text` | No | PK |  | SHA-256 of the session cookie value. | US-01-007 AC1: server-side session (ADR-0009); only a hash is stored. |
| `user_id` | `uuid` | No | FK |  | Who is signed in. References `users.id`, on delete cascade. | US-01-007 AC1: the session carries the user's role. |
| `expires_at` | `timestamptz` | No |  |  | When the session stops working. | US-01-007 AC3: an expired session is treated as no session (401). |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `idx_sessions_user_id`: on (user_id). Serves sign-out-all and FK lookups on users.

### `settings`: Runtime settings (hot: no)

The single row of runtime settings shared by api, mcp and worker.

Serves US-01-002, US-01-004, US-01-006, US-01-016. Expected volume: exactly 1 row.

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `smallint` | No | PK | `1` | Always 1; the table is a singleton. | Eng review A4: one row every process reads. |
| `demo_today` | `date` | No |  |  | The business date every computation uses. | REQ-022, US-01-004 AC1 and AC3: clock read by all processes; seeded from DEMO_TODAY. |
| `sending_enabled` | `boolean` | No |  | `true` | Kill switch: false blocks every send path. | US-01-002 AC1: kill switch persisted (AC-US-01-006-1). |
| `autonomy_mode` | `text` | No |  | `'manual'` | manual, assisted or trusted. | US-01-016 AC1: Manual by default. |
| `llm_budget_micro_usd` | `bigint` | No |  | `2000000` | LLM budget in micro-dollars. | US-01-009 AC3: calls refused past budget; $2.00 default (Q-016). |
| `feature_whatsapp` | `boolean` | No |  | `false` | WhatsApp channel on; seeded from FEATURE_WHATSAPP. | REQ-092, AC-US-00-024-2: admin can switch it off at runtime. |
| `feature_voice` | `boolean` | No |  | `false` | Prepare Call on; seeded from FEATURE_VOICE. | REQ-092. |
| `feature_payment_link` | `boolean` | No |  | `false` | Payment link page on; seeded from FEATURE_PAYMENT_LINK. | REQ-092. |
| `feature_trusted_mode` | `boolean` | No |  | `false` | Trusted autonomy allowed. | REQ-092, AC-US-01-016-4. |
| `updated_at` | `timestamptz` | No |  | `now()` | Last change to the row. | Rule: audit columns; approval queue shows freshness. |

**Constraints**

- `chk_settings_singleton`: `id = 1`. Refuses a second settings row.
- `chk_settings_autonomy_mode`: `autonomy_mode IN ('manual','assisted','trusted')`. Refuses an unknown autonomy mode.
- `chk_settings_budget_nonneg`: `llm_budget_micro_usd >= 0`. Refuses a negative budget.

### `customers`: Customers (hot: no)

A B2B buyer that owes the business money.

Serves US-00-001, US-00-002, US-00-004, US-01-003. Expected volume: 50 seeded rows (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | US-00-001 AC1: invoices, messages and replies reference the customer. |
| `name` | `text` | No |  |  | Business name, e.g. ABC Distributors. **(personal data)** | REQ-005; AC-US-00-006-3 checks the name in drafts. |
| `email` | `text` | No |  |  | Address reminders are sent to (example.in in seed). **(personal data)** | REQ-005, AC-US-01-003-4, AC-US-00-013-2: drafts only go here. |
| `phone` | `text` | No |  |  | Phone for WhatsApp and calls. **(personal data)** | REQ-005; US-00-024, US-00-025. |
| `segment` | `text` | No |  |  | enterprise, mid_market or sme. | REQ-026: segment is a priority factor. |
| `credit_terms_days` | `integer` | No |  | `30` | Agreed days to pay. | REQ-005: credit terms; shown on the customer page. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_customers_name`: unique on (lower(name)). Serves customer-name guardrail lookup and CRM search (AC-US-00-006-3).

**Constraints**

- `chk_customers_segment`: `segment IN ('enterprise','mid_market','sme')`. Refuses a segment the priority weights do not know.
- `chk_customers_name_not_blank`: `btrim(name) <> ''`. Refuses a nameless customer the name guardrail cannot check.
- `chk_customers_credit_terms`: `credit_terms_days BETWEEN 0 AND 365`. Refuses negative or absurd terms.

### `invoices`: Invoices (hot: yes)

One invoice raised on a customer; the unit every reminder cites.

Serves US-00-001, US-00-005, US-00-006, US-00-016, US-00-019. Expected volume: 300 seeded rows (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-001-1: invoices are listed and cited by id internally. |
| `customer_id` | `uuid` | No | FK |  | Who owes it. References `customers.id`, on delete restrict. | REQ-007; AC-US-00-006-4 rejects another customer's invoice. |
| `number` | `text` | No | UK |  | Invoice number, e.g. INV-1021. | REQ-007; AC-US-00-006-3 looks drafts' numbers up here. |
| `invoice_date` | `date` | No |  |  | Date issued. | REQ-007. |
| `due_date` | `date` | No |  |  | Date payment is due. | REQ-010: days overdue = clock minus due date; AC-US-00-006-5 checks cited dates. |
| `amount_paise` | `bigint` | No |  |  | Invoice amount in paise. | REQ-002, REQ-007; AC-US-00-005-1: money is BIGINT paise. |
| `status` | `text` | No |  | `'unpaid'` | unpaid, partially_paid, paid or disputed; written only by allocation and dispute services. | REQ-009, AC-US-00-001-5; eng review A6. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |
| `updated_at` | `timestamptz` | No |  | `now()` | Last change to the row. | Rule: audit columns; approval queue shows freshness. |

**Indexes**

- `uq_invoices_number`: unique on (number). Serves draft verification looks up every cited number (AC-US-00-006-3).
- `idx_invoices_customer_id_due_date`: on (customer_id, due_date). Serves unpaid invoices per customer oldest first (AC-US-00-001-1, allocation order US-00-019).
- `idx_invoices_open_due_date`: on (due_date) where status <> 'paid'. Serves dashboard ageing and overdue totals over open invoices (US-00-003).

**Constraints**

- `chk_invoices_status`: `status IN ('unpaid','partially_paid','paid','disputed')`. Refuses a status outside REQ-009 (AC-US-00-001-5).
- `chk_invoices_amount_positive`: `amount_paise > 0`. Refuses a zero or negative invoice.
- `chk_invoices_dates`: `due_date >= invoice_date`. Refuses an invoice due before it was issued.
- `chk_invoices_number_shape`: `number ~ '^INV-[0-9]+$'`. Refuses a number the invoice-number regex cannot find in a draft.

### `payments`: Payments (hot: no)

Money received, from the bank feed, the payment link or entered by a collector.

Serves US-00-017, US-00-018, US-00-019, US-03-004. Expected volume: tens seeded, one per credit (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-017-1: one payment row per credit. |
| `customer_id` | `uuid` | Yes | FK |  | Matched customer; null while it needs human verification. References `customers.id`, on delete restrict. | AC-US-00-017-2: ambiguous credits stay unmatched. |
| `amount_paise` | `bigint` | No |  |  | Amount received in paise. | REQ-011; AC-US-00-019-1. |
| `received_on` | `date` | No |  |  | Business date the money arrived: clock.today() at ingest, never the webhook timestamp. | Q-003: match window against claimed or promised date; promise check (AC-US-00-020-1). |
| `reference` | `text` | Yes |  |  | Bank or UTR reference text. | REQ-076: match by reference; allocation to a referenced invoice (AC-US-00-019-2). |
| `source` | `text` | No |  |  | bank_feed, payment_link or manual. | US-00-017, US-03-004: same ledger service for every source. |
| `bank_event_id` | `text` | Yes | UK |  | Bank feed event id for idempotency. | AC-US-00-017-4: a duplicate event creates no second payment. |
| `match_status` | `text` | No |  |  | matched or needs_verification. | AC-US-00-017-2: "Needs human verification". |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_payments_bank_event_id`: unique on (bank_event_id) where bank_event_id IS NOT NULL. Serves webhook dedupe (AC-US-00-017-4).
- `idx_payments_customer_id_received_on`: on (customer_id, received_on). Serves claim verification and promise check search a customer's payments in a date window (US-00-018, US-00-020).

**Constraints**

- `chk_payments_amount_positive`: `amount_paise > 0`. Refuses a zero or negative payment.
- `chk_payments_source`: `source IN ('bank_feed','payment_link','manual')`. Refuses an unknown money source.
- `chk_payments_match_status`: `match_status IN ('matched','needs_verification')`. Refuses an unknown match state.
- `chk_payments_matched_has_customer`: `match_status <> 'matched' OR customer_id IS NOT NULL`. Refuses a matched payment with no customer.
- `chk_payments_bank_event`: `source <> 'bank_feed' OR bank_event_id IS NOT NULL`. Refuses a bank-feed payment that cannot be deduplicated.

### `payment_allocations`: Payment allocations (hot: no)

The part of a payment applied to one invoice.

Serves US-00-001, US-00-019. Expected volume: one to three per payment (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-001-4: amount paid is the sum of allocations. |
| `payment_id` | `uuid` | No | FK |  | The payment being applied. References `payments.id`, on delete cascade. | AC-US-00-019-1. |
| `invoice_id` | `uuid` | No | FK |  | The invoice it pays. References `invoices.id`, on delete restrict. | AC-US-00-019-1, AC-US-00-001-4. |
| `amount_paise` | `bigint` | No |  |  | Amount applied in paise. | AC-US-00-019-1: 30,000,000 paise to INV-1021. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_payment_allocations_payment_invoice`: unique on (payment_id, invoice_id). Serves one allocation per payment and invoice.
- `idx_payment_allocations_invoice_id`: on (invoice_id). Serves invoice_balances view sums allocations per invoice (AC-US-00-001-4).

**Constraints**

- `chk_payment_allocations_amount_positive`: `amount_paise > 0`. Refuses an empty or negative allocation.

### `agent_runs`: Agent runs (hot: no)

One bounded orchestrator run for one customer.

Serves US-01-001, US-00-008, US-01-011. Expected volume: 15 per daily run plus one per reply (10^3 after a month).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-008-1: run id. |
| `customer_id` | `uuid` | No | FK |  | The customer the run is about. References `customers.id`, on delete restrict. | AC-US-00-008-1. |
| `run_date` | `date` | No |  |  | Demo-clock date the run belongs to. | AC-US-01-001-7: one scheduled run per date; eng review failure mode (clock read once). |
| `trigger` | `text` | No |  |  | scheduled, manual, reply or payment. | AC-US-01-001-7; flows A to C. |
| `status` | `text` | No |  | `'running'` | running or finished. | AC-US-01-001-5: re-entry refused while running. |
| `outcome` | `text` | Yes |  |  | WAIT_FOR_APPROVAL, ESCALATED, STOPPED_LIMIT, NO_ACTION or FAILED. | REQ-035, AC-US-00-008-1. |
| `tool_call_count` | `smallint` | No |  | `0` | Tool calls made. | REQ-032, AC-US-01-001-4. |
| `action` | `text` | Yes |  |  | Action selected, e.g. send_reminder. | REQ-030, AC-US-01-001-2. |
| `channel` | `text` | Yes |  |  | Channel selected. | REQ-030. |
| `tone` | `text` | Yes |  |  | Tone selected by code. | REQ-031, AC-US-01-001-3. |
| `reason` | `text` | Yes |  |  | Why the action or stop. | REQ-035; AC-US-01-001-4 records the limit reason. |
| `started_at` | `timestamptz` | No |  | `now()` | Start time. | REQ-035 timestamps. |
| `finished_at` | `timestamptz` | Yes |  |  | End time. | REQ-035 timestamps. |

**Indexes**

- `uq_agent_runs_scheduled_per_day`: unique on (customer_id, run_date) where trigger = 'scheduled'. Serves one scheduled run per customer per date (AC-US-01-001-7).
- `uq_agent_runs_running_customer`: unique on (customer_id) where status = 'running'. Serves refuse re-entry while a run is active (AC-US-01-001-5).
- `idx_agent_runs_customer_id_started_at`: on (customer_id, started_at). Serves latest runs on the customer page and admin list (US-00-008, US-01-006).

**Constraints**

- `chk_agent_runs_trigger`: `trigger IN ('scheduled','manual','reply','payment')`. Refuses an unknown trigger.
- `chk_agent_runs_status`: `status IN ('running','finished')`. Refuses an unknown run status.
- `chk_agent_runs_outcome`: `outcome IS NULL OR outcome IN ('WAIT_FOR_APPROVAL','ESCALATED','STOPPED_LIMIT','NO_ACTION','FAILED')`. Refuses an outcome the trajectory viewer cannot show.
- `chk_agent_runs_tool_limit`: `tool_call_count BETWEEN 0 AND 4`. Refuses a run that exceeded the 4-call bound (REQ-032).
- `chk_agent_runs_finished`: `(status = 'finished') = (outcome IS NOT NULL AND finished_at IS NOT NULL)`. Refuses a finished run without an outcome, or an outcome on a running run.
- `chk_agent_runs_channel`: `channel IS NULL OR channel IN ('email','whatsapp','voice')`. Refuses an unknown channel.
- `chk_agent_runs_tone`: `tone IS NULL OR tone IN ('gentle','firm','final')`. Refuses an unknown tone.

### `agent_steps`: Agent steps (hot: no)

One tool call inside a run, with redacted arguments.

Serves US-00-008, US-01-011. Expected volume: up to 4 per run (10^3).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-008-1: one step per tool call. |
| `agent_run_id` | `uuid` | No | FK |  | The run. References `agent_runs.id`, on delete cascade. | AC-US-00-008-1. |
| `seq` | `smallint` | No |  |  | Order within the run, 1 to 4. | AC-US-00-008-3: steps render in order. |
| `role` | `text` | No |  |  | collections, reply_understanding, payment_verification or escalation. | REQ-034, AC-US-01-001-6. |
| `tool_name` | `text` | No |  |  | Tool called. | AC-US-00-008-1; AC-US-01-011-1 compares tool sequences. |
| `arguments_redacted` | `jsonb` | No |  | `'{}'::jsonb` | Arguments with PII replaced by [redacted:*]. | REQ-036, AC-US-00-008-2. |
| `result_summary` | `text` | No |  |  | One-line result. | REQ-035. |
| `error_code` | `text` | Yes |  |  | Typed error code when the tool failed. | REQ-041. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_agent_steps_run_seq`: unique on (agent_run_id, seq). Serves steps of a run in order (AC-US-00-008-3).

**Constraints**

- `chk_agent_steps_seq`: `seq BETWEEN 1 AND 4`. Refuses a fifth executed step (REQ-032).
- `chk_agent_steps_role`: `role IN ('collections','reply_understanding','payment_verification','escalation')`. Refuses a role outside REQ-034.

### `messages`: Messages (hot: yes)

A drafted, approved, sent or rejected outbound message.

Serves US-00-005, US-00-009, US-00-010, US-00-011, US-01-002, US-00-024. Expected volume: about 15 per daily run (10^3).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-009-1: queue item id; send idempotency key (AC-US-00-011-2). |
| `customer_id` | `uuid` | No | FK |  | Recipient customer. References `customers.id`, on delete restrict. | AC-US-00-013-2: only this customer's address is used. |
| `agent_run_id` | `uuid` | Yes | FK |  | Run that drafted it; null for statement drafts from the UI. References `agent_runs.id`, on delete set null. | AC-US-00-009-1: link to trajectory. |
| `kind` | `text` | No |  |  | reminder, followup, statement or dispute_ack. | US-00-015, US-00-016 AC4, US-00-020 AC4. |
| `channel` | `text` | No |  |  | email, whatsapp or voice. | REQ-014. |
| `tone` | `text` | No |  |  | gentle, firm or final. | REQ-014, REQ-031. |
| `status` | `text` | No |  | `'draft'` | draft, pending_approval, approved, rejected, sent or failed. | REQ-014, AC-US-00-011-4. |
| `subject` | `text` | No |  |  | Email subject (names the customer). **(personal data)** | AC-US-00-011-1. |
| `body` | `text` | No |  |  | Final text after placeholders were filled. **(personal data)** | AC-US-00-005-2; guardrails run on it. |
| `version` | `integer` | No |  | `1` | Incremented on every edit. | CEO review D2: stale edit gets 409; AC-US-00-010-3. |
| `verified_version` | `integer` | Yes |  |  | Version that last passed guardrails. | AC-US-00-010-3: approve refused unless verified_version = version. |
| `guardrail_report` | `jsonb` | Yes |  |  | Per-token verification result shown in the queue. | AC-US-00-009-5. |
| `approved_by` | `uuid` | Yes | FK |  | Who approved. References `users.id`, on delete restrict. | AC-US-00-009-2. |
| `approved_at` | `timestamptz` | Yes |  |  | When approved. | AC-US-00-009-2. |
| `rejected_reason` | `text` | Yes |  |  | Why rejected. | AC-US-00-009-3. |
| `sent_at` | `timestamptz` | Yes |  |  | When delivered to the channel. | AC-US-00-011-1. |
| `send_attempts` | `smallint` | No |  | `0` | Delivery attempts. | AC-US-00-011-3: failed after retry limit. |
| `last_error` | `text` | Yes |  |  | Last delivery error code; IN_FLIGHT while a send is claimed, UNCONFIRMED if the worker died mid-send. | AC-US-00-011-2 and AC-US-00-011-3: a claimed send is never auto-retried (at most once, critic MAJOR 2). |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |
| `updated_at` | `timestamptz` | No |  | `now()` | Last change to the row. | Rule: audit columns; approval queue shows freshness. |

**Indexes**

- `idx_messages_status_created_at`: on (status, created_at) where status IN ('pending_approval','approved'). Serves approval queue and approved-ready list (US-00-009, AC-US-00-003-3).
- `idx_messages_customer_id_created_at`: on (customer_id, created_at). Serves messages on the customer page (US-00-004).
- `idx_messages_agent_run_id`: on (agent_run_id). Serves trajectory link and FK lookups.

**Constraints**

- `chk_messages_status`: `status IN ('draft','pending_approval','approved','rejected','sent','failed')`. Refuses a status outside REQ-014 (AC-US-00-011-4).
- `chk_messages_kind`: `kind IN ('reminder','followup','statement','dispute_ack')`. Refuses an unknown message kind.
- `chk_messages_channel`: `channel IN ('email','whatsapp','voice')`. Refuses an unknown channel.
- `chk_messages_tone`: `tone IN ('gentle','firm','final')`. Refuses a tone outside REQ-031.
- `chk_messages_rejected_reason`: `status <> 'rejected' OR (rejected_reason IS NOT NULL AND btrim(rejected_reason) <> '')`. Refuses a rejection with no reason (AC-US-00-009-3).
- `chk_messages_approved_verified`: `status NOT IN ('approved','sent') OR verified_version = version`. Refuses an approved or sent message whose current text never passed guardrails (REQ-057).
- `chk_messages_sent_at`: `(status = 'sent') = (sent_at IS NOT NULL)`. Refuses a sent message with no send time, or a send time on an unsent message.

### `message_invoices`: Invoices cited by a message (hot: no)

The invoices a draft covers.

Serves US-00-005, US-00-016. Expected volume: about 2 per message (10^3).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `message_id` | `uuid` | No | PK, FK |  | The message. References `messages.id`, on delete cascade. | AC-US-00-005-2: the draft cites these invoices. |
| `invoice_id` | `uuid` | No | PK, FK |  | A cited invoice. References `invoices.id`, on delete restrict. | AC-US-00-016-2: a disputed invoice is excluded from new drafts. |

**Indexes**

- `idx_message_invoices_invoice_id`: on (invoice_id). Serves which drafts cite a newly disputed invoice (AC-US-00-016-2).

### `replies`: Customer replies (hot: no)

A customer's reply and its classification.

Serves US-03-001, US-00-012, US-00-013. Expected volume: 40 seeded plus one per reply (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-03-001-1: stored reply. |
| `customer_id` | `uuid` | No | FK |  | Who replied. References `customers.id`, on delete restrict. | AC-US-03-001-1. |
| `message_id` | `uuid` | Yes | FK |  | Message it answers; null for seeded history. References `messages.id`, on delete set null. | AC-US-03-001-1 and AC-US-03-001-2 (mismatch refused). |
| `body` | `text` | No |  |  | Reply text, untrusted. **(personal data)** | REQ-068; eval input. |
| `received_at` | `timestamptz` | No |  | `now()` | When it arrived. | Timeline order (AC-US-00-022-3). |
| `classification` | `text` | Yes |  |  | One of the seven classes, null until classified. | REQ-064, AC-US-00-012-1. |
| `amount_paise` | `bigint` | Yes |  |  | Amount parsed in code from the text. | REQ-065, AC-US-00-012-3. |
| `stated_date` | `date` | Yes |  |  | Date resolved against the demo clock. | AC-US-00-012-2 and AC-US-00-012-4. |
| `invoice_refs` | `text[]` | No |  | `'{}'` | Invoice numbers mentioned. | REQ-065. |
| `confidence` | `numeric(3,2)` | Yes |  |  | Classifier confidence 0.00 to 1.00. | REQ-067, AC-US-00-012-5. |
| `recommended_action` | `text` | Yes |  |  | Next action chosen by code. | REQ-065. |
| `needs_review` | `boolean` | No |  | `false` | True when routed to a human. | AC-US-00-012-5, AC-US-00-013-1. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `idx_replies_customer_id_received_at`: on (customer_id, received_at). Serves replies on the customer page and timeline.
- `idx_replies_message_id`: on (message_id). Serves FK lookups from messages.

**Constraints**

- `chk_replies_classification`: `classification IS NULL OR classification IN ('PROMISE','PART_PAYMENT','DISPUTE','STATEMENT_REQUEST','PAYMENT_CONFIRMATION','NO_INTENT_UNCLEAR','OTHER_NOISE')`. Refuses a label outside the seven classes (AC-US-00-012-1).
- `chk_replies_confidence`: `confidence IS NULL OR confidence BETWEEN 0 AND 1`. Refuses a confidence outside 0 to 1.
- `chk_replies_amount_positive`: `amount_paise IS NULL OR amount_paise > 0`. Refuses a zero or negative parsed amount.

### `promises`: Promises to pay (hot: no)

A customer's commitment to pay an amount by a date.

Serves US-00-014, US-00-020, US-00-021. Expected volume: tens (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-014-1. |
| `customer_id` | `uuid` | No | FK |  | Who promised. References `customers.id`, on delete restrict. | REQ-069. |
| `reply_id` | `uuid` | Yes | FK |  | Reply it came from; null for seeded history. References `replies.id`, on delete set null. | AC-US-00-014-1. |
| `amount_paise` | `bigint` | No |  |  | Promised amount in paise. | REQ-069; AC-US-00-020-1 compares payments to it. |
| `promised_date` | `date` | No |  |  | Date promised. | REQ-069; AC-US-00-021-1 lists today's promises. |
| `status` | `text` | No |  | `'pending'` | pending, fulfilled, partially_fulfilled or missed. | REQ-012, AC-US-00-014-3. |
| `resolved_at` | `timestamptz` | Yes |  |  | When the promise check settled it. | AC-US-00-020-1 to AC-US-00-020-3. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `idx_promises_status_promised_date`: on (status, promised_date). Serves promise check and today's promises (US-00-020, US-00-021).
- `idx_promises_customer_id`: on (customer_id). Serves promises on the customer page; missed-promise priority factor (REQ-026).

**Constraints**

- `chk_promises_status`: `status IN ('pending','fulfilled','partially_fulfilled','missed')`. Refuses a status outside REQ-012 (AC-US-00-014-3).
- `chk_promises_amount_positive`: `amount_paise > 0`. Refuses an empty promise.
- `chk_promises_resolved`: `(status = 'pending') = (resolved_at IS NULL)`. Refuses a settled promise without a time, or a pending one with one.

### `promise_invoices`: Invoices a promise covers (hot: no)

Link from a promise to the invoices it pays.

Serves US-00-014. Expected volume: one to three per promise (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `promise_id` | `uuid` | No | PK, FK |  | The promise. References `promises.id`, on delete cascade. | REQ-069: invoices on the promise. |
| `invoice_id` | `uuid` | No | PK, FK |  | A covered invoice. References `invoices.id`, on delete restrict. | AC-US-00-014-2: oldest first when none named. |

**Indexes**

- `idx_promise_invoices_invoice_id`: on (invoice_id). Serves FK lookups from invoices.

### `disputes`: Disputes (hot: no)

A customer's contest of one invoice.

Serves US-00-016. Expected volume: a few (10^1).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-016-1. |
| `customer_id` | `uuid` | No | FK |  | Who disputes. References `customers.id`, on delete restrict. | REQ-072. |
| `invoice_id` | `uuid` | No | FK |  | The invoice disputed. References `invoices.id`, on delete restrict. | REQ-072, AC-US-00-016-1. |
| `reply_id` | `uuid` | Yes | FK |  | Reply that raised it. References `replies.id`, on delete set null. | AC-US-00-016-1. |
| `reason` | `text` | No |  |  | Reason in a short phrase, e.g. quantity mismatch. | REQ-072. |
| `status` | `text` | No |  | `'open'` | open or resolved. | REQ-013, AC-US-00-016-5. |
| `resolution_note` | `text` | Yes |  |  | How it was resolved. | AC-US-00-016-5. |
| `resolved_at` | `timestamptz` | Yes |  |  | When resolved. | AC-US-00-016-5. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_disputes_open_invoice`: unique on (invoice_id) where status = 'open'. Serves one open dispute per invoice; drafting excludes it (AC-US-00-016-2).
- `idx_disputes_customer_id`: on (customer_id). Serves disputes on the customer page and dashboard count.

**Constraints**

- `chk_disputes_status`: `status IN ('open','resolved')`. Refuses a status outside REQ-013.
- `chk_disputes_resolved`: `(status = 'resolved') = (resolved_at IS NOT NULL)`. Refuses a resolved dispute with no time.

### `escalations`: Escalations (hot: no)

A case handed to a human.

Serves US-00-016, US-00-012, US-00-013, US-00-017, US-00-018. Expected volume: tens (10^2).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-016-3. |
| `customer_id` | `uuid` | No | FK |  | Customer concerned. References `customers.id`, on delete restrict. | AC-US-03-001-3. |
| `kind` | `text` | No |  |  | dispute, low_confidence, injection_suspected, claim_not_found or payment_needs_verification. | AC-US-00-016-3, AC-US-00-012-5, AC-US-00-013-1, AC-US-00-018-2, AC-US-00-017-2. |
| `reason` | `text` | No |  |  | Human-readable reason. | AC-US-03-001-3. |
| `dispute_id` | `uuid` | Yes | FK |  | Source dispute. References `disputes.id`, on delete set null. | AC-US-00-016-3. |
| `reply_id` | `uuid` | Yes | FK |  | Source reply. References `replies.id`, on delete set null. | AC-US-00-012-5. |
| `payment_id` | `uuid` | Yes | FK |  | Source payment. References `payments.id`, on delete set null. | AC-US-00-017-2. |
| `status` | `text` | No |  | `'open'` | open or resolved. | AC-US-03-001-3. |
| `resolved_by` | `uuid` | Yes | FK |  | Who closed it. References `users.id`, on delete restrict. | Timeline actor for human actions. |
| `resolved_at` | `timestamptz` | Yes |  |  | When closed. | Dashboard open counts. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `idx_escalations_status_created_at`: on (status, created_at) where status = 'open'. Serves open escalations on the dashboard (US-00-003).
- `idx_escalations_customer_id`: on (customer_id). Serves escalations on the customer page.
- `idx_escalations_dispute_id`: on (dispute_id). Serves FK lookups.
- `idx_escalations_reply_id`: on (reply_id). Serves FK lookups.
- `idx_escalations_payment_id`: on (payment_id). Serves FK lookups.

**Constraints**

- `chk_escalations_kind`: `kind IN ('dispute','low_confidence','injection_suspected','claim_not_found','payment_needs_verification')`. Refuses an unknown escalation kind.
- `chk_escalations_status`: `status IN ('open','resolved')`. Refuses an unknown status.
- `chk_escalations_resolved`: `(status = 'resolved') = (resolved_at IS NOT NULL)`. Refuses a resolved escalation with no time.

### `guardrail_events`: Guardrail events (hot: no)

A record of one guardrail refusal.

Serves US-00-006, US-00-007, US-01-002, US-01-006, US-01-012. Expected volume: tens per run in red-team tests (10^3).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-006-6: one row per rejection. |
| `check_name` | `text` | No |  |  | Which check refused, e.g. amount. | AC-US-00-006-6. |
| `code` | `text` | No |  |  | Typed error code, e.g. AMOUNT_MISMATCH. | REQ-049, REQ-053. |
| `customer_id` | `uuid` | Yes | FK |  | Customer concerned, if any. References `customers.id`, on delete set null. | Admin list and timeline. |
| `message_id` | `uuid` | Yes | FK |  | Message concerned, if any. References `messages.id`, on delete set null. | AC-US-00-006-6. |
| `agent_run_id` | `uuid` | Yes | FK |  | Run concerned, if any. References `agent_runs.id`, on delete set null. | AC-US-01-001-4. |
| `detail` | `jsonb` | No |  | `'{}'::jsonb` | Offending token and expected value, no PII bodies. | AC-US-00-006-6: the offending token. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `idx_guardrail_events_created_at`: on (created_at). Serves last 20 failures on the admin page (AC-US-01-006-2).
- `idx_guardrail_events_customer_id`: on (customer_id). Serves FK lookups.
- `idx_guardrail_events_message_id`: on (message_id). Serves guardrail history for a draft.
- `idx_guardrail_events_agent_run_id`: on (agent_run_id). Serves FK lookups.

### `llm_calls`: LLM calls (hot: no)

One model call through the gateway with tokens and cost.

Serves US-01-008, US-01-009. Expected volume: up to 60 per run plus evals (10^4).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-01-009-1. |
| `agent_run_id` | `uuid` | Yes | FK |  | Run that made the call; null for evals. References `agent_runs.id`, on delete set null. | Admin cost per run. |
| `prompt_name` | `text` | No |  |  | Prompt registry name. | Eng review Q3: replay key. |
| `prompt_version` | `integer` | No |  |  | Prompt version. | Eng review Q3; AC-US-01-008-4. |
| `model` | `text` | No |  |  | Model id used. | AC-US-01-008-1. |
| `mode` | `text` | No |  |  | live, replay or record. | REQ-098; AC-US-01-009-4. |
| `replay_key` | `text` | No |  |  | name@vN:sha256 of normalised input. | AC-US-01-008-4. |
| `input_tokens` | `integer` | No |  | `0` | Prompt tokens. | AC-US-01-009-1. |
| `output_tokens` | `integer` | No |  | `0` | Completion tokens. | AC-US-01-009-1. |
| `cost_micro_usd` | `bigint` | No |  | `0` | Cost in micro-dollars (integer). | AC-US-01-009-1: 4,500 for the reference call. |
| `latency_ms` | `integer` | Yes |  |  | Wall time. | HLD section 8: measure latency. |
| `error_code` | `text` | Yes |  |  | LLM_UPSTREAM, LLM_TIMEOUT, BUDGET_EXHAUSTED or REPLAY_MISS. | AC-US-01-008-3, AC-US-01-008-5. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `idx_llm_calls_created_at`: on (created_at). Serves running total and admin spend (AC-US-01-009-2).
- `idx_llm_calls_agent_run_id`: on (agent_run_id). Serves cost per run.

**Constraints**

- `chk_llm_calls_mode`: `mode IN ('live','replay','record')`. Refuses an unknown gateway mode.
- `chk_llm_calls_nonneg`: `input_tokens >= 0 AND output_tokens >= 0 AND cost_micro_usd >= 0`. Refuses negative usage.

### `timeline_events`: Timeline events (hot: yes)

One state change about a customer, for the timeline.

Serves US-00-022, US-00-004. Expected volume: tens per customer (10^4).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | No | PK | `gen_random_uuid()` | Surrogate key. | AC-US-00-022-1. |
| `customer_id` | `uuid` | No | FK |  | Whose timeline. References `customers.id`, on delete cascade. | AC-US-00-022-3. |
| `occurred_at` | `timestamptz` | No |  | `now()` | Wall time of the change. | AC-US-00-022-3: time order. |
| `business_date` | `date` | No |  |  | Demo-clock date of the change. | REQ-022: the story spans 30 Sep to 05 Oct on the demo clock. |
| `kind` | `text` | No |  |  | Event kind from the REQ-081 list. | AC-US-00-022-1. |
| `actor` | `text` | No |  |  | ai, human, system or customer. | AC-US-00-022-3. |
| `actor_user_id` | `uuid` | Yes | FK |  | Human actor. References `users.id`, on delete set null. | AC-US-00-009-2. |
| `amount_paise` | `bigint` | Yes |  |  | Amount shown on the event. | AC-US-00-022-3. |
| `ref_type` | `text` | Yes |  |  | Kind of the related record. | Link from the event to its record. |
| `ref_id` | `uuid` | Yes |  |  | Id of the related record. | Link from the event to its record. |
| `summary` | `text` | No |  |  | One-line text, no reply bodies. | AC-US-00-022-3; REQ-113 keeps bodies out. |

**Indexes**

- `idx_timeline_events_customer_id_occurred_at`: on (customer_id, occurred_at). Serves customer timeline in order (AC-US-00-022-3).
- `idx_timeline_events_actor_user_id`: on (actor_user_id). Serves FK lookups.

**Constraints**

- `chk_timeline_events_actor`: `actor IN ('ai','human','system','customer')`. Refuses an actor outside AC-US-00-022-3.
- `chk_timeline_events_kind`: `kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced')`. Refuses an event kind the timeline cannot render (REQ-081).
- `chk_timeline_events_ref`: `(ref_type IS NULL) = (ref_id IS NULL)`. Refuses a half-filled reference.

### `jobs`: Background jobs (hot: yes)

One unit of background work for the worker.

Serves US-01-001, US-00-011, US-00-020. Expected volume: tens per day (10^3).

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `bigint` | No | PK | `generated always as identity` | Job id. | ADR-0006. |
| `kind` | `text` | No |  |  | daily_run, promise_check or send_message. | ADR-0006; AC-US-01-001-7. |
| `dedupe_key` | `text` | No |  |  | run date or message id. | AC-US-01-001-7 and AC-US-00-011-2: no duplicate run or send. |
| `payload` | `jsonb` | No |  | `'{}'::jsonb` | Job arguments (ids only). | ADR-0006. |
| `status` | `text` | No |  | `'queued'` | queued, running, done or dead. | ADR-0006: retries and dead letters. |
| `attempts` | `smallint` | No |  | `0` | Attempts so far. | AC-US-00-011-3: retry limit. |
| `max_attempts` | `smallint` | No |  | `5` | Attempts allowed: 5 means the first try plus 4 retries. | AC-US-00-011-3. |
| `run_at` | `timestamptz` | No |  | `now()` | Earliest time to run (backoff). | ADR-0006. |
| `locked_at` | `timestamptz` | Yes |  |  | When a worker took it. | ADR-0006: stale-lock recovery. |
| `last_error` | `text` | Yes |  |  | Last error code. | Admin job view. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Indexes**

- `uq_jobs_kind_dedupe_key`: unique on (kind, dedupe_key). Serves idempotent enqueue (AC-US-01-001-7, AC-US-00-011-2).
- `idx_jobs_status_run_at`: on (run_at) where status = 'queued'. Serves worker poll with SKIP LOCKED (ADR-0006).

**Constraints**

- `chk_jobs_kind`: `kind IN ('daily_run','promise_check','send_message')`. Refuses an unknown job kind.
- `chk_jobs_status`: `status IN ('queued','running','done','dead')`. Refuses an unknown job status.
- `chk_jobs_attempts`: `attempts BETWEEN 0 AND max_attempts`. Refuses attempts beyond the limit.

### `idempotency_keys`: Idempotency keys (hot: no)

The stored response for a POST replayed with the same Idempotency-Key.

Serves US-03-001, US-01-005, US-00-017, US-03-004. Expected volume: one per creating POST (10^3); purged by reset.

| Column | Type | Null | Key | Default | Description | Why |
| --- | --- | --- | --- | --- | --- | --- |
| `key` | `text` | No | PK |  | Client-supplied Idempotency-Key. | api/openapi.yaml: Idempotency-Key required on creating POSTs; a repeat returns the first response. |
| `route` | `text` | No | PK |  | Method and path template the key was used on. | The same key on two routes means two different requests. |
| `request_sha256` | `text` | No |  |  | Hash of the request body. | A repeat key with a different body is 409, not a replay. |
| `status_code` | `smallint` | No |  |  | First response status. | Replay returns the same status. |
| `response_body` | `jsonb` | No |  |  | First response body (ids and codes, no PII bodies). | Replay returns the same body. |
| `created_at` | `timestamptz` | No |  | `now()` | When the row was written. | Rule: audit columns (postgres reference). |

**Constraints**

- `chk_idempotency_keys_status`: `status_code BETWEEN 200 AND 599`. Refuses a status that is not an HTTP status.

### View `invoice_balances`

`paid_paise` = sum of allocations, `remaining_paise` = amount minus paid, per invoice (REQ-008, AC-US-00-001-4). Status stays a column written only by the allocation and dispute services in the same transaction; a service test asserts it agrees with the view after the seed and after the ABC story (eng review A6).

## 5. Enumerations

Closed sets are CHECK constraints on text (brief section 6), each named `chk_<table>_<rule>` above: invoice status (REQ-009), message status, kind, channel, tone (REQ-014, REQ-031), reply classification (REQ-064), promise status (REQ-012), dispute status (REQ-013), escalation kind and status, run trigger, status and outcome (REQ-035), step role (REQ-034), timeline kind and actor (REQ-081, AC-US-00-022-3), job kind and status (ADR-0006), payment source and match status, customer segment, user role, autonomy mode, gateway mode. Each is closed because a screen, a guardrail or a test switches on its values.

## 6. Retention and personal data

| Table | Lifetime | Rule | Mechanism |
| --- | --- | --- | --- |
| every table except users, sessions, llm_calls | until the next demo reset | demo data only | `make reset-demo` truncates and reseeds |
| sessions | until `expires_at` | sign-in lifetime | checked on each request; expired rows removed on sign-in |
| users, llm_calls | UNDEFINED | none stated for real use | owner question: how long to keep cost and user records outside the demo (suggest 1 year for llm_calls) |

Personal-data columns (8): `users.email`, `users.display_name`, `customers.name`, `customers.email`, `customers.phone`, `messages.subject`, `messages.body`, `replies.body`. Seed data is synthetic (`example.in`). Logs and timeline summaries never copy these values (REQ-113); trajectory arguments are redacted (REQ-036). `privacy-review` (Phase 9) sets real-use retention.

## 7. Migration plan

1. `0001_initial_schema`: applies `docs/design/schema.sql` (new database; expand only). Downgrade drops every object in reverse FK order. No hot table exists yet, so no batching or concurrent index builds are needed.
2. Later changes: one Alembic revision each, expand then contract, written by `db-migration` with a tested downgrade.

## 8. Rules and deviations

Rules checked: 14 (uuid keys, timestamptz audit columns, NOT NULL by default, FK with explicit ON DELETE, index on every referencing column, named CHECKs, named indexes, partial indexes for queue and open-row predicates, money as integer minor units, no `now()` in predicates, citext or lower() for case-insensitive uniqueness, one transaction per schema file, comments on every table and column, derived values in views not triggers).

- deviation: no `tenant_id` on any table, because the product is single-tenant (PRD non-goal, Q-014).
- deviation: `updated_at` only where rows change after creation (settings, invoices, messages); append-only tables have `created_at` only.
- deviation: `timeline_events.ref_type`/`ref_id` is a polymorphic reference without a foreign key, because one event can point at any of seven tables; the service writes both in the same transaction as the referenced row.

## 9. What the review found

Reviewed with the HLD critic (2026-09-30); findings that touch the schema were fixed here: `settings.feature_*` columns (runtime flags), `messages.last_error` IN_FLIGHT and UNCONFIRMED semantics (at-most-once send), `payments.received_on` from the demo clock. The companion files are generated from one spec (`.scratch/gen_datamodel.py`, kept out of git); edit the spec and regenerate rather than editing one file.

## 10. Open concerns

- [gap] Retention for real use is UNDEFINED for users and llm_calls. Owner: Savitha Sista. Date: before any non-demo use. Blocks development: no.
- [risk] `timeline_events.ref_id` has no FK; a bug could leave a dangling reference. Owner: Claude Code. Date: services task. Blocks development: no.

## 11. Applying this

data-model: 21 tables, 186 columns, 40 indexes, 53 checks, 0 enums, 8 personal-data columns, 0 problems
schema-apply: docs/design/schema.sql applied to postgres:17-alpine, 21 tables
