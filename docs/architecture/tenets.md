# System design tenets: CollectionsAgent

Rules this team holds itself to on this project. Each is here because somebody could plausibly do the opposite, and a reviewer can point at a breach.

## 1. The ledger computes every number

**No amount, total, balance or date shown to a customer or collector comes from model output; it comes from a SQL query or a service function over the ledger.**

The brief's non-negotiable 2 and objective B2. The model writes prose around `{{invoice_table}}` and `{{total}}` (ADR-0007, REQ-004).

_A breach looks like:_ a prompt that asks the model to "state the total outstanding", with the model's text saved as the draft.

## 2. Money is integer paise until the last formatter

**Every money column is BIGINT paise, every API field is an integer paise value, and only the INR formatter (one in Python for message text, one in TypeScript for the UI, both tested against tests/vectors/inr.json) produces ₹ strings.**

Floats and pre-formatted strings are where rounding and lakh-grouping bugs hide (REQ-002, REQ-003).

_A breach looks like:_ a new `amount_rupees: float` field on an API response, or `toLocaleString` called in a component.

## 3. Services are the only writers

**Every state change goes through a service function that writes the change, its TimelineEvent and any GuardrailEvent in one transaction; API handlers, MCP tools, jobs and the orchestrator call services and never write SQL.**

Three entry points share one database (eng review A1); duplicated writes make the timeline and guardrails drift.

_A breach looks like:_ an approve endpoint that runs `UPDATE messages SET status='approved'` directly.

## 4. Nothing sends without passing the send gate

**Every send path calls one `send_gate` check (approved or Trusted allow-list, kill switch off, guardrails current for this text version) and refuses otherwise.**

Three send paths exist (API, worker, MCP `send_message`); REQ-043, REQ-058, REQ-099.

_A breach looks like:_ a "resend" admin button that calls the channel adapter directly.

## 5. Business dates come from the demo clock

**Business code reads the date only through `clock.today()`; a lint test fails on `date.today()` or `datetime.now()` for business dates elsewhere.**

The demo advances time live (REQ-022, REQ-023; ADR-0006 schedule keys use it).

_A breach looks like:_ days overdue computed with `date.today()` in a dashboard query helper.

## 6. Tests never need the network

**`make check` passes with no OpenRouter key, no network, no real mail, WhatsApp or bank; model calls run in replay and a missing fixture fails with REPLAY_MISS instead of calling out.**

Non-negotiable 5 (REQ-106).

_A breach looks like:_ a test marked `skipif(not OPENROUTER_API_KEY)` that silently does nothing in CI.
