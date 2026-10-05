# Collections Employee upgrade: design (Phase 2)

Status: built on develop, 2026-10-04 (HACK-003, uncommitted). Migrations 0002 to 0007. Section 9 lists where the
build differs from this design.
Scope: the 8 features, "Why?" panels and the AI Safety Center from the upgrade brief, added on top of the
existing P0 to P2 product. Read with `docs/architecture/tenets.md`, `docs/design/collections-lld.md`.

## 1. What we keep, unchanged

Every new surface plugs into these; none is bypassed or weakened.

| Existing control | Where | How new features use it |
| --- | --- | --- |
| Ledger computes every number (tenet 1) | `services/ledger.py`, `invoice_balances` view | Calls, memory, portal, CFO, follow-ups read figures from SQL only |
| Services are the only writers, with a timeline event (tenet 3) | `services/*`, `services/timeline.record` | Every new write is a service function that also records the event |
| Send gate (tenet 4) | `approval.send_gate` | SMS, WhatsApp and voice-call placement go through it; no new send path |
| Guardrails `verify()` | `guardrails/verify.py` | Call scripts, follow-up drafts, memory recall lines are verified like drafts |
| Untrusted customer text | `agent/classify.py` (rules + model labels, code parses spans) | Voice transcripts and portal text use the same `classify()` and injection patterns |
| Bounded agent, 4 calls, tool registry | `agent/orchestrator.py`, `tools/registry.py` | New tools are registered there with the same tiers in `policy/guardrails.yaml` |
| Kill switch, autonomy modes, Trusted allow-list | `settings` row, `approval.trusted_approve` | Follow-ups and calls respect them; Trusted already refuses missed-promise customers |
| Roles Viewer / Collector / Admin | `api/deps.py` | Same matrix: viewers read, collectors act, admins configure |
| HMAC-signed links and webhooks | `services/paylink.py`, `payments.verify_signature` | Portal tokens and provider webhooks follow the same pattern |

## 2. Decisions taken by default (change any before approval)

1. **No new dependencies.** Twilio REST calls with the installed `httpx`; Twilio webhook signatures
   (HMAC-SHA1 over URL plus sorted params) with stdlib `hmac`. Charts reuse `components/charts.tsx`.
2. **Model calls stay on the existing gateway** (OpenRouter, Claude Haiku 4.5, replay mode in tests).
   The model only labels and copies spans; code parses amounts and dates. No raw reasoning is stored
   or shown; "Why?" shows decision factors computed by code.
3. **Priority score keeps its formula** so ABC stays at 66 HIGH (README demo). Explainability adds the
   points each factor contributed and two zero-point context factors ("No active dispute",
   "No response to last reminder"). A changed formula is a separate decision.
4. **Dispute lifecycle widens** `open -> assigned -> investigating -> resolved`. Every query that means
   "dispute still active" changes from `status = 'open'` to `status <> 'resolved'` (7 places, listed in 4.7).
5. **Calls are not recorded.** Only the speech-to-text turns the provider returns are stored, after a
   spoken disclosure. Recording needs `VOICE_RECORDING_ENABLED=true` and a customer "yes" to the consent
   prompt; otherwise no recording parameter is sent to the provider.
6. **Real vs simulated is a property of the provider object** (`provider.simulated: bool`), stored on each
   message and call row, and shown as a badge. The UI never infers it.

## 3. Delivery: 6 slices, one task branch each

The brief is too large for one reviewable change (estimate below). Each slice ends with `make check`
green, its integration tests, the ABC story intact, and a self-review against section 6.

| Slice | Features | Why this order | Size |
| --- | --- | --- | --- |
| S1 | F4 priority explainability, "Why?" panels | Smallest; other slices reuse the factor component | S |
| S2 | F8 CFO dashboard, AI Safety Center | Read-only SQL; no new write paths; big demo value | M |
| S3 | F7 dispute intelligence and routing, F5 automatic follow-up | Both extend existing state machines (disputes, promises) | M |
| S4 | F3 customer memory, F2 omnichannel layer (email, SMS, WhatsApp) | Memory feeds the drafts the channel layer sends | L |
| S5 | F1 voice agent (provider abstraction, simulated + Twilio) | Needs the S4 channel layer and S3 follow-ups | L |
| S6 | F6 customer portal | New public auth surface; last, with a security pass of its own | M |

Rough size: 3 new migrations' worth of schema, about 25 backend files touched or added, 10 frontend files,
and 60 to 80 new tests.

## 4. Per-feature design

### 4.1 F4 Priority and risk scoring (S1)

- **Plugs into** `services/priority.py`. `score()` additionally returns `factors: list[Factor]`
  (`code, label, value, points, direction`), where `points` is the exact term that factor added to `raw`.
  The sum of points minus the dispute deduction equals the score (tested).
- **Context factors** (0 points): `NO_ACTIVE_DISPUTE`; `NO_RESPONSE` when the last sent message has no
  reply after it (SQL on `messages.sent_at` vs `replies.received_at`).
- **API**: `Priority` gains `factors`; `/customers`, `/customers/{id}` and `/dashboard` already return
  `Priority`, so this is additive. OpenAPI regenerated (drift test).
- **UI**: a `WhyPanel` component in `kit.tsx` (factor, value, points bar, the rule text) on Customer,
  Customers and Today. Header copy: "Decision factors and rules. Not model reasoning."
- **Tests (first)**: points sum equals score for the 5 seeded customers; ABC shows 66 HIGH with the
  brief's five factors; no-response detection.

### 4.2 "Why?" for every AI action (S1, extended per slice)

- One shape everywhere: `Explanation {title, factors[], rules[], data_sources[]}`, built by code.
- Sources: priority factors (4.1); agent runs (tone rule from `select_tone`, channel rule from the cadence
  policy, tools called from `agent_steps`); reply classification (class, confidence, the copied spans,
  `source=llm|rules`, threshold); dispute routing (category rule matched, team); follow-up (promise row,
  payments counted, autonomy mode).
- No `agent_steps` prose from the model is shown; only tool names, redacted arguments and outcomes,
  which the run viewer already displays.

### 4.3 F8 CFO / executive dashboard (S2)

- **Backend**: `services/executive.py`, read-only SQL, `GET /api/v1/executive` (Reader).
  Definitions, stated on the page:
  - Total receivables: sum of `remaining_paise`.
  - Overdue: remaining on invoices past due.
  - Collected this month: matched payments with `received_on` in the demo clock's month.
  - At risk: remaining on invoices that are disputed, or belong to HIGH-band customers, or have a missed promise.
  - Promises due today / missed: sums of `promises.amount_paise` by status and date.
  - Collection rate: collected this month divided by (collected this month plus overdue now).
  - Series: ageing buckets (exists), collections by week (8 weeks), overdue trend (recomputed per week
    end from invoices and allocations dated on or before it), promise fulfilment rate, risk band
    distribution, collections by channel (payment `source`, and message channel of the last contact
    before payment), disputes by category and status, expected collections (pending promises by week).
- **UI**: new route `#/executive`, KPI row with `Figure`, charts with `ColumnChart` and `ProportionBar`,
  "What needs attention today" list where every row carries its `Explanation`.
- **Tests**: each metric against hand-computed seed values; a payment moves "collected" and "rate".

### 4.4 AI Safety Center (S2)

- **Backend**: `services/safety.py`, `GET /api/v1/safety` (Reader). Every metric is a count of real rows:
  messages verified (`guardrail_report` not null), guardrail failures by code (`guardrail_events`),
  incorrect amounts blocked (`AMOUNT_MISMATCH`, `TOTAL_MISMATCH` codes), prompt attacks
  (`PROMPT_INJECTION_SUSPECTED`), human approvals (`approved_by` not null), automatic sends
  (approved with `approved_by` null), send-gate refusals, kill switch state, autonomy mode, LLM spend.
- Seeded demo rows are labelled: the seed writes guardrail events with `detail.seed = true`, and the page
  shows "includes N DEMO events" next to any count that contains them.
- **UI**: `#/safety`, Admin and Viewer can read; kill switch toggle stays on Admin (existing endpoint).

### 4.5 F7 Dispute intelligence and routing (S3)

- **Schema** (migration 0002): `disputes.category` (invoice_error, wrong_quantity, wrong_price,
  duplicate_invoice, missing_delivery, service_issue, contract_issue, other), `assigned_team`
  (billing, operations, sales, legal_contracts, collections), `assigned_to uuid null`, status widened to
  `open, assigned, investigating, resolved`; unique open index becomes `WHERE status <> 'resolved'`.
  New `dispute_events` is not needed: transitions are timeline events (`dispute_assigned`,
  `dispute_investigating`, `dispute_resolved`).
- **Classification**: rules first (extend `DISPUTE_KINDS` to the 8 categories), the model may suggest a
  category through the existing classify prompt; code keeps it only if it is one of the 8. Routing is a
  fixed table in `policy/guardrails.yaml` (`dispute_routing: {wrong_quantity: operations, ...}`).
- **Lifecycle**: `collections.transition_dispute(id, to, user)`; allowed moves are a table in code;
  `resolved` needs a human user id and a note. No tool exposes resolve; the registry test asserts it.
  An `auto_resolve` rule list in policy is empty by default (the brief's "deterministic rule" hook).
- **Queries changed to `<> 'resolved'`**: `priority.py:83`, `overview.py:70`, `overview.py:145`,
  `approval.py:390`, `collections.py:187`, `send_gate`'s dispute join, and the schema's unique index.
- **UI**: disputes table on Customer and a Disputes queue (category, team, status stepper, Why?).
- **Tests**: category rules for each of 8, routing table, every legal and illegal transition, a tool or
  AI actor cannot resolve, reminders stay paused for every non-resolved status.

### 4.6 F5 Automatic follow-up (S3)

- **Plugs into** `payments.evaluate_promises` (already marks fulfilled, partially fulfilled, missed on
  clock advance, payment and the daily `promise_check` job).
- **Schema**: `follow_up_tasks (id, customer_id, promise_id, kind, due_on, status open|done|cancelled,
  recommended_action, message_id null, created_at, closed_by, closed_at)`; unique per promise.
- **On missed or partially fulfilled**, in the same transaction: create the task; record
  `followup_created`. Then, outside it, a `followup_draft` job asks the Collections role for a follow-up
  draft (kind `followup`) that cites the promise via memory (4.7).
- **Autonomy**: Manual creates the task only; Assisted also drafts (waits for approval); Trusted drafts,
  and `trusted_approve` still refuses because the customer has a missed promise (policy
  `no_missed_promise: true`). So no follow-up is ever auto-sent unless the engineer changes that policy.
- **UI**: "Missed promise" card (promised, date, received from ledger, status, recommended action, Why?)
  on Today and Customer; task list with Done and Snooze.
- **Tests**: fulfilled, partial, missed, autonomy mode respected in all three, idempotent on re-evaluation.

### 4.7 F3 Customer memory (S4)

- **Service** `services/memory.py`: `memory(customer_id) -> Memory`, assembled only from rows:
  timeline events, promises (with status), payments, disputes (category only), messages (subject,
  channel, status), call summaries, collector notes. Read-only.
- **Notes**: `customer_notes (id, customer_id, author_id, body, created_at)`; internal only, never sent to
  the model or the portal.
- **Use in drafts**: the model never writes the recall line. Code renders a `{{promise_recall}}`
  placeholder from the promise row ("On 20 Sep 2026 you mentioned that ₹3,00,000 would be paid on
  05 Oct 2026. We have not received it yet."), and `verify()` checks those figures against
  `promise_amounts`/`promise_dates` as it already does.
- **MCP / tools**: `get_customer_memory` (read tier) returning the same summaries `history()` returns
  today plus the recall facts; no reply bodies (T-18).
- **Tests**: previous promise cited with ledger values; a reply claiming "we promised ₹1 lakh" does not
  change any figure; notes never appear in tool output.

### 4.8 F2 Omnichannel (S4)

- **Abstraction**: extend the existing `MessageChannel` protocol in `channels/` (it already has `name`
  and `send`) with `simulated: bool`. Providers: `EmailChannel` (exists, real SMTP),
  `TwilioSmsChannel`, `TwilioWhatsAppChannel` (real when `TWILIO_*` set), `SimulatedChannel(name)` that
  writes to a local outbox table instead of the network. Chosen once at startup in `channels/__init__.py`.
- **Service** `services/communication.py` (`CollectionCommunicationService` in the brief): picks the
  next channel from a cadence policy in `policy/guardrails.yaml`
  (`day 1 email, day 3 whatsapp, day 7 voice, day 10 human`, measured from the first reminder of the
  current cycle), honours `customers.preferred_channel` and channel feature flags, and returns
  `next_channel` with its `Explanation`. It never sends; drafts go through approval and `send_gate`.
- **Schema**: `messages.channel` adds `sms`; `messages.simulated boolean`; `customers.preferred_channel`,
  `customers.contact_consent jsonb` (per channel opt-in); timeline kinds widen.
- **Send gate** gains: channel flag on (SMS, WhatsApp, voice), customer consent for that channel.
- **UI**: Customer header shows preferred channel, last contacted channel and date, response status,
  next recommended channel (with Why?); channel badge with REAL or SIMULATED on every message.
- **Tests**: cadence selection per day, preference override, approval required for each channel, timeline
  entry per send, simulated flag stored and shown, SMS length and no-link rule.

### 4.9 F1 Voice collections agent (S5)

```
Collector clicks Call -> calls.request (Collector role, kill switch, feature_voice, consent, no open dispute)
 -> call row 'requested' -> send_gate-style call_gate -> VoiceProvider.place(call)
 Twilio:   POST /api/v1/webhooks/voice/{call_id}/turn   (X-Twilio-Signature verified)
           returns TwiML <Say> script line + <Gather input="speech">
 Simulated: the console's "Customer says" box posts turns to the same service function
 -> conversation.turn(call_id, transcript) -> classify() (same rules, model labels, injection check)
 -> next line from a fixed script state machine, figures from the ledger, verified by verify()
 -> on end: call summary, outcome, promise/dispute/escalation via the existing services
```

- **Schema**: `calls (id, customer_id, requested_by, provider, simulated, status requested|ringing|
  in_progress|completed|failed|no_answer|wrong_number, outcome, consent_recording boolean,
  provider_call_id, started_at, ended_at, summary, follow_up_on)`, `call_turns (call_id, seq, speaker
  ai|customer, text, classification, created_at)`. Timeline kinds `call_requested`, `call_completed`,
  `call_failed`.
- **What the AI may say**: a fixed script per state (intro with disclosure, reason with ledger total,
  answer: balance, invoice list, due dates, payment link offer; confirm promise; close). Each line is
  rendered by code from ledger values and verified. The model only classifies the customer's turn.
  "Friday" is resolved by `clock.resolve_date`, so "₹2 lakh this Friday" becomes ₹2,00,000 on a date.
- **Intents** map to existing actions: PROMISE -> `log_promise`; DISPUTE -> `log_dispute` + routing;
  STATEMENT_REQUEST (invoice) -> statement draft for approval; payment link request -> pay-link draft for
  approval; WRONG_NUMBER / UNAVAILABLE (new classes) -> call outcome + escalation; other -> summary only.
  Injection text ends the call politely and escalates.
- **Twilio provider**: REST `Calls.json` via `httpx`, credentials from env; signature check on every
  webhook; unknown `call_id` or bad signature returns 403 with no body detail.
- **Consent**: the intro states the call is from an automated assistant; recording only as in decision 5.
- **UI**: Call button (Collector, Admin) with REAL or SIMULATED badge; call view with turns, summary,
  outcome, created promise, Why?; call history on Customer and timeline.
- **Tests**: initiation (gates: kill switch, flag, role, dispute), each intent from a transcript,
  "₹2 lakh this Friday" -> ₹2,00,000 and the right date, failed and no-answer, injection in a transcript,
  bad Twilio signature, summary content comes from rows.

### 4.10 F6 Customer portal (S6)

- **Token**: `P.<customer_uuid>.<exp>.<hmac>` with purpose `portal` in the MAC input, so a pay-link token
  cannot be replayed as a portal token or the reverse. 7-day TTL (as pay links). Created by a Collector,
  stored only as a hash in `portal_links (id, customer_id, token_sha256, expires_at, revoked_at)`, so a
  link can be revoked.
- **Public API** `/api/v1/portal/{token}` (GET summary; POST `promise`, `dispute`, `help`; POST `pay`
  reuses `paylink.pay` per invoice). Responses use dedicated Pydantic models with only: customer name,
  open invoices (number, dates, remaining), total. No notes, risk, reasoning, timeline, other customers.
  A test asserts the response schema's field set.
- **Writes**: promise -> `log_promise(actor='customer')` with amount at most the outstanding and date
  within the policy window; dispute -> `log_dispute` for an invoice of this customer only, text through
  `classify`'s injection check and the 500-char cap; help -> escalation. Rate limit per token in the DB.
- **UI**: `#/portal/<token>` public page, separate layout, labelled "Payment: SIMULATED" while the pay
  provider is simulated.
- **Tests**: valid, invalid, expired, revoked, tampered customer id, another customer's invoice,
  injection text, response field allow-list.

## 5. Real vs simulated after the upgrade

| Part | Status |
| --- | --- |
| Ledger, priority, factors, guardrails, approvals, audit timeline, payment matching, follow-up rules, dispute routing, memory, CFO metrics, Safety Center counts | Real |
| Email | Real SMTP (Mailpit locally) |
| SMS, WhatsApp, voice calls | Real when `TWILIO_*` is set and the flag is on; otherwise SIMULATED provider, badge on every row |
| Payment link and portal Pay Now | SIMULATED (no payment processor) |
| Bank feed | SIMULATED (signed credits through the real webhook) |
| Customer replies by email | Entered by a collector (D-001 stays open) |

## 6. Security checklist applied to each slice

Prompt injection on every new text input (transcript, SMS/WhatsApp reply, portal text); no tool resolves a
dispute, changes a balance or marks paid; portal response field allow-list; token purpose separation and
expiry; webhook signatures (Twilio) verified before parsing; role checks on every new route; no secrets in
code, `.env.example` updated; `/security-review` or `cso --diff` per slice; `bearing:branch-review`.

## 7. New environment variables

`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_WHATSAPP_FROM`,
`VOICE_PUBLIC_BASE_URL` (the URL Twilio calls back), `VOICE_RECORDING_ENABLED` (default false),
`FEATURE_SMS` (default false), `PORTAL_LINK_TTL_DAYS` (default 7). Secrets documented with placeholders only.

## 8. Testing and verification limits in this environment

The coding sandbox cannot reach Docker, so Postgres integration tests (`make test-integration`), `make eval`
and Playwright (`make e2e`) can only run on the engineer's machine or in CI. Each slice reports them as
"not run" until they are run there.

## 9. Where the build differs from the design

- Portal tokens are 256 random bits; the database keeps only their SHA-256 with an expiry, a revocation time and a
  20-write cap. That gives revocation and purpose separation without an HMAC format.
- Calls are never recorded, so `VOICE_RECORDING_ENABLED` was not added. `PORTAL_LINK_TTL_DAYS` is a constant (7).
- Follow-up drafts are made in the same transaction as the missed promise, not by a separate job.
- The simulated SMS and WhatsApp providers write no outbox table; the message row carries `simulated = true` and the
  timeline line says SIMULATED.
- Internal notes have their own table (`customer_notes`, migration 0005) and timeline kind `note_added`.
- Dispute routing assigns the team automatically (status `assigned`); people move it to `investigating` and only
  people resolve it. No `auto_resolve` rule is configured.
- Each new migration applies `app/db/upgrade_NNNN.sql` and `downgrade_NNNN.sql`; `schema.sql` and migration 0001
  are unchanged, and the demo reset reads the upgrade files to find the new tables.
- Voice webhooks also require the `CallSid` Twilio sends to match the call's stored provider id.
