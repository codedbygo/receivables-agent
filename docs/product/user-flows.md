# User flows

Backlog: docs/product/backlog.md   Built: 2026-09-30
Flows: 13   Screens named: 11 (Dashboard, Customer page, Approval queue, Draft editor, Trajectory viewer, Reply simulator, Admin, Evaluation, CRM list, Prepare Call, Payment link)

Platform for every flow: desktop web (the brief names no mobile client), plus terminal for the admin and MCP flows.

## Flow F1: Start the day and find who to chase (EP-01)

Persona: Collector, group 00   Platforms: desktop web
Trigger: the collector starts work on the demo date.
Exercises: US-00-001, US-00-002, US-00-003, US-00-004, US-00-023

### Before it starts

- Seed loaded and clock at 30 Sep 2026 (US-01-003, US-01-004).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Dashboard | opens the console | shows totals, ageing buckets and the attention list, amounts as ₹ with lakh grouping | US-00-003, US-00-023 |
| 2 | Dashboard | clicks ABC Distributors under high priority | opens the customer page | US-00-003 |
| 3 | Customer page | reads the priority panel | shows score, HIGH band and the three reasons | US-00-002 |
| 4 | Customer page | reads invoices | shows INV-1021, INV-1034, INV-1047 with days overdue and ₹7,50,000 outstanding | US-00-001 |
| 5 | Customer page | reads the recommended next action | shows "Send follow-up on missed promise" | US-00-004 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | a group in the attention list is empty | the group shows its empty state | US-00-003 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | database unavailable | "Cannot load data. The service is starting or down." | admin checks `/readyz` | US-01-014 |

### End state

The collector knows who to chase and why.

## Flow F2: The daily run prepares verified drafts (EP-02)

Persona: Admin, group 01   Platforms: desktop web
Trigger: 09:00 IST on the demo date, or the admin presses Run now.
Exercises: US-01-001, US-00-005, US-00-006, US-00-007, US-00-008

### Before it starts

- Gateway in replay or live mode with budget left (US-01-008, US-01-009).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Admin | presses Run now | starts one run over the top 15 | US-01-001 |
| 2 | (background) | none | for ABC: reads history, picks firm tone and email, asks the model for prose with placeholders | US-01-001, US-00-005 |
| 3 | (background) | none | fills the invoice table and total from the ledger | US-00-005 |
| 4 | (background) | none | verifies numbers, names, dates and tone; queues the draft as pending_approval | US-00-006, US-00-007 |
| 5 | Trajectory viewer | opens ABC's run | shows each tool call, redacted, and outcome WAIT_FOR_APPROVAL | US-00-008 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 2 | the agent needs a fifth tool call | stops with STOPPED_LIMIT; no draft | US-01-001 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 4 | a number does not match | draft rejected, GuardrailEvent in admin, "guardrail failed" on timeline | the run moves on to the next customer | US-00-006 |
| 2 | budget exhausted | run stops calling the model; admin shows BUDGET_EXHAUSTED | raise budget or switch to replay | US-01-009 |

### End state

Verified drafts wait in the approval queue.

## Flow F3: Approve, edit or reject and send (EP-03)

Persona: Collector, group 00   Platforms: desktop web
Trigger: drafts are waiting in the approval queue.
Exercises: US-00-009, US-00-010, US-00-011, US-01-002

### Before it starts

- At least one pending draft (F2).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Approval queue | opens ABC's draft | shows context, reasons, draft and trajectory link | US-00-009 |
| 2 | Approval queue | presses Approve | marks approved, writes timeline | US-00-009 |
| 3 | (background) | none | worker sends once over SMTP; MailHog shows the email; status sent | US-00-011 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 2 | wants to change wording | opens Draft editor, saves; guardrails re-run; returns to step 2 | US-00-010 |
| 2 | draft is wrong | Reject with a reason; draft closed | US-00-009 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 2 | edit introduces a wrong amount | "AMOUNT_MISMATCH: ₹4,50,000 is not the ledger amount for INV-1021" | fix the text | US-00-010 |
| 3 | MailHog down | status failed, timeline entry | worker retries after recovery | US-00-011 |
| 3 | kill switch on | message stays approved; "Sending is paused" banner | admin turns sending back on | US-01-002 |

### End state

The customer has the reminder, once.

## Flow F4: A reply becomes a promise (EP-04)

Persona: Collector, group 00   Platforms: desktop web
Trigger: the customer replies to the reminder.
Exercises: US-03-001, US-00-012, US-00-013, US-00-014, US-00-015

### Before it starts

- ABC's reminder sent (F3).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Reply simulator | pastes "We can pay ₹3 lakh on October 5 and the remaining amount later." | stores the reply against ABC and the message | US-03-001 |
| 2 | (background) | none | classifies PROMISE, parses ₹3,00,000 and 05 Oct 2026 in code | US-00-012 |
| 3 | Customer page | reads the timeline | shows "promise logged ₹3,00,000 for 05 Oct 2026" | US-00-014 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 2 | STATEMENT_REQUEST | a statement draft enters the queue | US-00-015 |
| 2 | DISPUTE | continues in F5 | US-00-016 |
| 2 | PAYMENT_CONFIRMATION | continues in F6 alternate path | US-00-018 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 2 | confidence below threshold | escalation "Low-confidence classification" | collector reads and records by hand | US-00-012 |
| 2 | reply contains instructions | GuardrailEvent PROMPT_INJECTION_SUSPECTED; no action | collector reviews | US-00-013 |

### End state

The promise is pending and tracked.

## Flow F5: A dispute goes to a human (EP-05)

Persona: Collector, group 00   Platforms: desktop web
Trigger: the customer contests an invoice.
Exercises: US-00-016

### Before it starts

- ABC has INV-1047 unpaid.

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Reply simulator | pastes the dispute about INV-1047 | classifies DISPUTE | US-00-016 |
| 2 | (background) | none | logs the dispute, marks INV-1047 disputed, creates escalation | US-00-016 |
| 3 | Dashboard | sees it under disputes | links to ABC | US-00-016 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 3 | collector resolves it | dispute resolved; reminders resume | US-00-016 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | invoice not named | dispute logged on the customer, escalation asks the collector to pick the invoice | collector sets it | US-00-016 |

### End state

INV-1047 is not chased; a human owns the case.

## Flow F6: Payment arrives and the promise is kept (EP-06)

Persona: Collector, group 00   Platforms: desktop web
Trigger: the bank feed posts a credit.
Exercises: US-00-017, US-00-018, US-00-019, US-00-020, US-00-021

### Before it starts

- ABC's promise ₹3,00,000 for 05 Oct pending (F4); clock advanced to 05 Oct (F8).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Admin | posts a simulated credit ₹3,00,000 from ABC | verifies signature, stores payment, auto-matches ABC | US-00-017 |
| 2 | (background) | none | allocates to INV-1021; outstanding ₹4,50,000 | US-00-019 |
| 3 | Dashboard | presses Check payment in Today's promises | promise fulfilled | US-00-021, US-00-020 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | customer claims "already paid" instead | claim checked against ledger; matched or escalated | US-00-018 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | two candidate customers | payment "Needs human verification" in attention list | collector allocates | US-00-017 |
| 3 | no payment by next day | promise missed, ⚠ badge, follow-up proposed | next run drafts follow-up | US-00-020 |

### End state

Ledger, invoice and promise agree.

## Flow F7: Read the whole story (EP-07)

Persona: Collector, group 00   Platforms: desktop web
Trigger: the collector wants the history before a call.
Exercises: US-00-022

### Before it starts

- Events exist for the customer.

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Customer page | scrolls the timeline | shows every event in order with icon, amount and actor | US-00-022 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | a new customer with no events | timeline shows only "invoice due" events | US-00-022 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | a state change wrote no event | caught by the test in AC-US-00-022-2 before release | fix the service | US-00-022 |

### End state

The collector knows the full history.

## Flow F8: Prepare and run the demo (EP-08)

Persona: Admin, group 01   Platforms: terminal, desktop web
Trigger: before a demo or rehearsal.
Exercises: US-01-003, US-01-004, US-01-005, US-01-006, US-01-007

### Before it starts

- Stack up (F12).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | terminal | runs `make demo` | reseeds and sets ABC at the story start, clock 30 Sep | US-01-005, US-01-003 |
| 2 | Admin | signs in as admin | admin screen with sending, mode, cost, runs | US-01-007, US-01-006 |
| 3 | Admin | advances the clock 5 days | clock 05 Oct; promise check runs | US-01-004 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | mid-demo reset needed | Reset demo data button does the same | US-01-005 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 2 | a collector opens settings | 403 "Admins only" | sign in as admin | US-01-007 |

### End state

The demo is at a known starting point.

## Flow F9: Model calls stay in budget and replayable (EP-09)

Persona: Admin, group 01   Platforms: terminal
Trigger: the network or budget fails during a demo.
Exercises: US-01-008, US-01-009

### Before it starts

- Fixtures recorded for the demo path.

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | terminal | sets `LLM_MODE=replay` and restarts api and worker | every model call answers from fixtures; cost 0 | US-01-008, US-01-009 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | live mode and budget left | calls go to OpenRouter and cost is logged | US-01-009 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | fixture missing | REPLAY_MISS with the key | record it with `LLM_MODE=record` | US-01-008 |

### End state

The demo continues without the network.

## Flow F10: Claude Code drives the tools (EP-10)

Persona: MCP client, group 03   Platforms: terminal
Trigger: an engineer registers the MCP server in Claude Code.
Exercises: US-03-002, US-03-003

### Before it starts

- Stack up; registration snippet run.

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | Claude Code | asks for overdue customers | `list_overdue` returns schema-valid results | US-03-002 |
| 2 | Claude Code | asks to send ABC's draft | `send_message` refuses NOT_APPROVED | US-03-002 |
| 3 | Claude Code | asks for an invoice | `get_invoice` returns it | US-03-003 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 2 | draft approved and sending on | message sends once | US-03-002 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | bad argument | VALIDATION_ERROR with the field | fix the call | US-03-002 |

### End state

The external agent worked inside the same rules.

## Flow F11: Check the numbers before shipping (EP-11)

Persona: Admin, group 01   Platforms: terminal, desktop web
Trigger: a prompt or code change, or CI.
Exercises: US-01-010, US-01-011, US-01-012

### Before it starts

- Labelled replies, scenarios and red-team set committed.

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | terminal | runs `make eval` | prints reply metrics, scenario pass count, red-team N/N | US-01-010, US-01-011, US-01-012 |
| 2 | Evaluation | opens the page | shows the same numbers as `docs/evals/report.md` | US-01-010 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | run in CI | replay mode, fails on regression | US-01-010 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 1 | a red-team draft passes | "red-team: 14/15 rejected" and a failing exit | fix the guardrail | US-01-012 |

### End state

The quality numbers are known and published.

## Flow F12: Clone, start and follow the README (EP-12)

Persona: Admin, group 01   Platforms: terminal, desktop web
Trigger: a judge or new engineer clones the repository.
Exercises: US-01-013, US-01-014, US-01-015, US-00-023

### Before it starts

- Docker installed.

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | terminal | follows How to run | six services healthy | US-01-013 |
| 2 | terminal | curls `/readyz` | 200 with each dependency ok | US-01-014 |
| 3 | Dashboard | follows How to demo | the ABC story completes; screens in light or dark | US-01-015, US-00-023 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 1 | no OpenRouter key | runs in replay mode | US-01-013 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 2 | Postgres not ready | `/readyz` 503 naming the database | wait or `make down up` | US-01-014 |

### End state

A new person has run and demoed the system.

## Flow F13: Use the extended channels (EP-13)

Persona: Collector, group 00   Platforms: desktop web
Trigger: the admin enables P2 flags for a longer demo.
Exercises: US-00-024, US-00-025, US-03-004, US-00-026, US-01-016

### Before it starts

- Flags on (US-01-016).

### Steps

| Step | Screen | The user | The system | Story |
| --- | --- | --- | --- | --- |
| 1 | CRM list | sorts by outstanding | lists all 50 customers | US-00-026 |
| 2 | Approval queue | approves a WhatsApp reminder | simulated outbox shows it sent | US-00-024 |
| 3 | Prepare Call | opens ABC's call sheet | summary, invoices, promises, talking points | US-00-025 |
| 4 | Payment link | customer pays INV-1034 | SIMULATED payment; invoice paid | US-03-004 |

### Alternate paths

| At step | Condition | What happens | Story |
| --- | --- | --- | --- |
| 2 | Trusted mode and an allow-listed gentle reminder | sends without approval | US-01-016 |

### When it fails

| At step | What goes wrong | What the user sees | Recovery | Story |
| --- | --- | --- | --- | --- |
| 2 | flag off | FEATURE_DISABLED; option hidden | admin enables flag | US-01-016 |

### End state

The P2 extras work and can be turned off before the main demo.
