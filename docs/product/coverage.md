# Coverage: PRD statements to stories

PRD: docs/product/PRD.md   Backlog: docs/product/backlog.md   Built: 2026-09-30

Generated from the AC `Covers:` lines in the backlog; the gate below recomputes it from the same lines.

## Matrix

| REQ | Statement (short) | Judgement | Why | Covered by | AC ids |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | The system lists each customer's unpaid invoices. | story | a user-visible capability that ships on its own | US-00-001 | AC-US-00-001-1 |
| REQ-002 | The system stores every money amount as integer paise. | story | a user-visible capability that ships on its own | US-00-005 | AC-US-00-005-1 |
| REQ-003 | The system formats money as INR with Indian digit grouping (`₹7 | story | a user-visible capability that ships on its own | US-00-023 | AC-US-00-023-1, AC-US-00-023-2 |
| REQ-004 | Every money amount | criterion-of US-00-005 | a rule or detail of the capability in US-00-005, tested by its AC, not a separate user action | US-00-005 | AC-US-00-005-4 |
| REQ-005 | The system stores for each customer: name | criterion-of US-00-001 | a rule or detail of the capability in US-00-001, tested by its AC, not a separate user action | US-00-001 | AC-US-00-001-2 |
| REQ-006 | The system derives each customer's total outstanding from the ledger. | criterion-of US-00-001 | a rule or detail of the capability in US-00-001, tested by its AC, not a separate user action | US-00-001 | AC-US-00-001-3 |
| REQ-007 | The system stores for each invoice: number | criterion-of US-00-001 | a rule or detail of the capability in US-00-001, tested by its AC, not a separate user action | US-00-001 | AC-US-00-001-1 |
| REQ-008 | The system derives an invoice's amount paid from payment allocations a | criterion-of US-00-001 | a rule or detail of the capability in US-00-001, tested by its AC, not a separate user action | US-00-001 | AC-US-00-001-4 |
| REQ-009 | An invoice's status is one of unpaid | criterion-of US-00-001 | a rule or detail of the capability in US-00-001, tested by its AC, not a separate user action | US-00-001 | AC-US-00-001-5 |
| REQ-010 | The system derives an invoice's days overdue from the demo clock. | criterion-of US-00-001 | a rule or detail of the capability in US-00-001, tested by its AC, not a separate user action | US-00-001 | AC-US-00-001-6 |
| REQ-011 | The system records payments and their allocations to invoices. | story | a user-visible capability that ships on its own | US-00-017 | AC-US-00-017-1 |
| REQ-012 | A promise's status is one of pending | story | a user-visible capability that ships on its own | US-00-014 | AC-US-00-014-3 |
| REQ-013 | A dispute's status is one of open | story | a user-visible capability that ships on its own | US-00-016 | AC-US-00-016-1, AC-US-00-016-5 |
| REQ-014 | A message records its channel | story | a user-visible capability that ships on its own | US-00-011 | AC-US-00-011-3, AC-US-00-011-4 |
| REQ-015 | The system stores customer replies and escalations. | story | a user-visible capability that ships on its own | US-03-001 | AC-US-03-001-1, AC-US-03-001-3 |
| REQ-016 | The system records each LLM call with its tokens and cost. | story | a user-visible capability that ships on its own | US-01-009 | AC-US-01-009-1 |
| REQ-017 | The system persists settings for kill switch | story | a user-visible capability that ships on its own | US-01-006 | AC-US-01-006-1 |
| REQ-018 | The seed creates 50 customers | story | a user-visible capability that ships on its own | US-01-003 | AC-US-01-003-1 |
| REQ-019 | Seed customers carry realistic Indian B2B names and invoice amounts be | criterion-of US-01-003 | a rule or detail of the capability in US-01-003, tested by its AC, not a separate user action | US-01-003 | AC-US-01-003-2 |
| REQ-020 | The seed includes customers that are hugely overdue | criterion-of US-01-003 | a rule or detail of the capability in US-01-003, tested by its AC, not a separate user action | US-01-003 | AC-US-01-003-3 |
| REQ-021 | Seed email addresses use `@example.in`-style demo domains only. | criterion-of US-01-003 | a rule or detail of the capability in US-01-003, tested by its AC, not a separate user action | US-01-003 | AC-US-01-003-4 |
| REQ-022 | All days-overdue | story | a user-visible capability that ships on its own | US-01-004 | AC-US-01-004-1, AC-US-01-004-2 |
| REQ-023 | An admin advances the demo clock by N days. | criterion-of US-01-004 | a rule or detail of the capability in US-01-004, tested by its AC, not a separate user action | US-01-004 | AC-US-01-004-3 |
| REQ-024 | An admin resets demo data to the seeded state. | story | a user-visible capability that ships on its own | US-01-005 | AC-US-01-005-1 |
| REQ-025 | `make demo` resets data to the start of the ABC Distributors story. | criterion-of US-01-005 | a rule or detail of the capability in US-01-005, tested by its AC, not a separate user action | US-01-005 | AC-US-01-005-2 |
| REQ-026 | Application code computes a priority score from amount overdue | story | a user-visible capability that ships on its own | US-00-002 | AC-US-00-002-1 |
| REQ-027 | The daily collection run selects the top 15 customers by priority. | criterion-of US-00-002 | a rule or detail of the capability in US-00-002, tested by its AC, not a separate user action | US-00-002 | AC-US-00-002-2 |
| REQ-028 | Each prioritised customer shows its score | criterion-of US-00-002 | a rule or detail of the capability in US-00-002, tested by its AC, not a separate user action | US-00-002 | AC-US-00-002-3, AC-US-00-002-4 |
| REQ-029 | The agent reads the customer's history before selecting an action. | story | a user-visible capability that ships on its own | US-01-001 | AC-US-01-001-1 |
| REQ-030 | The agent selects an action | criterion-of US-01-001 | a rule or detail of the capability in US-01-001, tested by its AC, not a separate user action | US-01-001 | AC-US-01-001-2 |
| REQ-031 | Application code selects the tone (gentle | criterion-of US-01-001 | a rule or detail of the capability in US-01-001, tested by its AC, not a separate user action | US-01-001 | AC-US-01-001-3 |
| REQ-032 | The agent makes at most 4 tool calls per customer per run; on reaching | criterion-of US-01-001 | a rule or detail of the capability in US-01-001, tested by its AC, not a separate user action | US-01-001 | AC-US-01-001-4 |
| REQ-033 | The agent never invokes another agent. | criterion-of US-01-001 | a rule or detail of the capability in US-01-001, tested by its AC, not a separate user action | US-01-001 | AC-US-01-001-5 |
| REQ-034 | One orchestrator runs the Collections | criterion-of US-01-001 | a rule or detail of the capability in US-01-001, tested by its AC, not a separate user action | US-01-001 | AC-US-01-001-6 |
| REQ-035 | Each agent run records run id | story | a user-visible capability that ships on its own | US-00-008 | AC-US-00-008-1 |
| REQ-036 | Tool arguments in the trajectory log have PII redacted. | criterion-of US-00-008 | a rule or detail of the capability in US-00-008, tested by its AC, not a separate user action | US-00-008 | AC-US-00-008-2 |
| REQ-037 | A collector views an agent run's trajectory in the UI. | criterion-of US-00-008 | a rule or detail of the capability in US-00-008, tested by its AC, not a separate user action | US-00-008 | AC-US-00-008-3 |
| REQ-038 | The MCP server exposes `list_overdue` | story | a user-visible capability that ships on its own | US-03-002 | AC-US-03-002-1 |
| REQ-039 | The MCP server exposes `get_invoice` | story | a user-visible capability that ships on its own | US-03-003 | AC-US-03-003-1, AC-US-03-003-2 |
| REQ-040 | Every MCP tool validates its input and output against a JSON schema. | criterion-of US-03-002 | a rule or detail of the capability in US-03-002, tested by its AC, not a separate user action | US-03-002 | AC-US-03-002-2, AC-US-03-002-3 |
| REQ-041 | Every MCP tool reports failures with a typed error code. | criterion-of US-03-002 | a rule or detail of the capability in US-03-002, tested by its AC, not a separate user action | US-03-002 | AC-US-03-002-2 |
| REQ-042 | No MCP tool accepts raw SQL or gives unrestricted database access. | criterion-of US-03-002 | a rule or detail of the capability in US-03-002, tested by its AC, not a separate user action | US-03-002 | AC-US-03-002-4 |
| REQ-043 | `send_message` refuses unless the message is approved (or allow-listed | criterion-of US-03-002 | a rule or detail of the capability in US-03-002, tested by its AC, not a separate user action | US-03-002 | AC-US-03-002-5 |
| REQ-044 | The MCP server serves stdio for Claude Code and streamable HTTP for th | criterion-of US-03-002 | a rule or detail of the capability in US-03-002, tested by its AC, not a separate user action | US-03-002 | AC-US-03-002-1 |
| REQ-045 | The repository provides a Claude Code registration snippet for the MCP | criterion-of US-03-002 | a rule or detail of the capability in US-03-002, tested by its AC, not a separate user action | US-03-002 | AC-US-03-002-6 |
| REQ-046 | A draft cites each invoice's number | criterion-of US-00-005 | a rule or detail of the capability in US-00-005, tested by its AC, not a separate user action | US-00-005 | AC-US-00-005-2 |
| REQ-047 | The LLM writes draft prose around placeholders (`{{invoice_table}}` | criterion-of US-00-005 | a rule or detail of the capability in US-00-005, tested by its AC, not a separate user action | US-00-005 | AC-US-00-005-3, AC-US-00-005-5 |
| REQ-048 | Before a draft is saved | story | a user-visible capability that ships on its own | US-00-006 | AC-US-00-006-1 |
| REQ-049 | The system rejects a draft whose extracted invoice numbers | criterion-of US-00-006 | a rule or detail of the capability in US-00-006, tested by its AC, not a separate user action | US-00-006 | AC-US-00-006-2, AC-US-00-006-3 |
| REQ-050 | The system rejects a draft that cites an invoice belonging to another  | criterion-of US-00-006 | a rule or detail of the capability in US-00-006, tested by its AC, not a separate user action | US-00-006 | AC-US-00-006-4 |
| REQ-051 | The system rejects a draft containing an impossible date. | criterion-of US-00-006 | a rule or detail of the capability in US-00-006, tested by its AC, not a separate user action | US-00-006 | AC-US-00-006-5 |
| REQ-052 | The system rejects a draft containing threats | story | a user-visible capability that ships on its own | US-00-007 | AC-US-00-007-1, AC-US-00-007-2 |
| REQ-053 | Every guardrail failure writes a GuardrailEvent. | criterion-of US-00-006 | a rule or detail of the capability in US-00-006, tested by its AC, not a separate user action | US-00-006 | AC-US-00-006-6 |
| REQ-054 | Each of the 15 guardrail cases in brief section 7 has an automated tes | criterion-of US-00-007 | a rule or detail of the capability in US-00-007, tested by its AC, not a separate user action | US-00-007 | AC-US-00-007-3 |
| REQ-055 | The approval queue shows customer | story | a user-visible capability that ships on its own | US-00-009 | AC-US-00-009-1, AC-US-00-009-5 |
| REQ-056 | A collector approves | criterion-of US-00-009 | a rule or detail of the capability in US-00-009, tested by its AC, not a separate user action | US-00-009 | AC-US-00-009-2, AC-US-00-009-3 |
| REQ-057 | An edited draft passes the guardrails again before it can be approved. | story | a user-visible capability that ships on its own | US-00-010 | AC-US-00-010-1, AC-US-00-010-2, AC-US-00-010-3 |
| REQ-058 | Every outbound message requires human approval | criterion-of US-00-009 | a rule or detail of the capability in US-00-009, tested by its AC, not a separate user action | US-00-009 | AC-US-00-009-4 |
| REQ-059 | An approved email message is sent over SMTP to the MailHog test inbox. | criterion-of US-00-011 | a rule or detail of the capability in US-00-011, tested by its AC, not a separate user action | US-00-011 | AC-US-00-011-1 |
| REQ-060 | A WhatsApp channel sends through a simulated | story | a user-visible capability that ships on its own | US-00-024 | AC-US-00-024-1, AC-US-00-024-2 |
| REQ-061 | A voice channel produces call preparation only and places no call. | story | a user-visible capability that ships on its own | US-00-025 | AC-US-00-025-2 |
| REQ-062 | An approved message is sent at most once. | criterion-of US-00-011 | a rule or detail of the capability in US-00-011, tested by its AC, not a separate user action | US-00-011 | AC-US-00-011-2 |
| REQ-063 | The system ingests a customer reply against the customer and message i | criterion-of US-03-001 | a rule or detail of the capability in US-03-001, tested by its AC, not a separate user action | US-03-001 | AC-US-03-001-1, AC-US-03-001-2 |
| REQ-064 | The system classifies a reply as PROMISE | story | a user-visible capability that ships on its own | US-00-012 | AC-US-00-012-1 |
| REQ-065 | A classification returns class | criterion-of US-00-012 | a rule or detail of the capability in US-00-012, tested by its AC, not a separate user action | US-00-012 | AC-US-00-012-2 |
| REQ-066 | Amounts and dates extracted from a reply are parsed and validated by a | criterion-of US-00-012 | a rule or detail of the capability in US-00-012, tested by its AC, not a separate user action | US-00-012 | AC-US-00-012-3, AC-US-00-012-4 |
| REQ-067 | A classification with low confidence goes to human review. | criterion-of US-00-012 | a rule or detail of the capability in US-00-012, tested by its AC, not a separate user action | US-00-012 | AC-US-00-012-5 |
| REQ-068 | Reply text is treated as untrusted input and instructions inside it ca | story | a user-visible capability that ships on its own | US-00-013 | AC-US-00-013-1, AC-US-00-013-2, AC-US-00-013-3 |
| REQ-069 | The system stores each promise with customer | criterion-of US-00-014 | a rule or detail of the capability in US-00-014, tested by its AC, not a separate user action | US-00-014 | AC-US-00-014-1, AC-US-00-014-2 |
| REQ-070 | A "Today's promises" panel lists promises due on the demo date with a  | story | a user-visible capability that ships on its own | US-00-021 | AC-US-00-021-1, AC-US-00-021-2 |
| REQ-071 | A missed promise shows a warning badge and a recommended next action. | story | a user-visible capability that ships on its own | US-00-020 | AC-US-00-020-4 |
| REQ-072 | On a dispute the system records its reason and invoice through `log_di | criterion-of US-00-016 | a rule or detail of the capability in US-00-016, tested by its AC, not a separate user action | US-00-016 | AC-US-00-016-1 |
| REQ-073 | The system drafts no reminders for a disputed invoice while the disput | criterion-of US-00-016 | a rule or detail of the capability in US-00-016, tested by its AC, not a separate user action | US-00-016 | AC-US-00-016-2 |
| REQ-074 | A dispute creates an escalation to a human. | criterion-of US-00-016 | a rule or detail of the capability in US-00-016, tested by its AC, not a separate user action | US-00-016 | AC-US-00-016-3 |
| REQ-075 | The system never sends the customer an argument about a disputed invoi | criterion-of US-00-016 | a rule or detail of the capability in US-00-016, tested by its AC, not a separate user action | US-00-016 | AC-US-00-016-4 |
| REQ-076 | A customer's payment claim is checked against the ledger by amount | story | a user-visible capability that ships on its own | US-00-018 | AC-US-00-018-1, AC-US-00-018-2 |
| REQ-077 | A simulated bank feed arrives through the webhook handler and auto-mat | criterion-of US-00-017 | a rule or detail of the capability in US-00-017, tested by its AC, not a separate user action | US-00-017 | AC-US-00-017-1, AC-US-00-017-2 |
| REQ-078 | The system never marks an invoice paid on a customer claim alone. | criterion-of US-00-018 | a rule or detail of the capability in US-00-018, tested by its AC, not a separate user action | US-00-018 | AC-US-00-018-2, AC-US-00-018-3 |
| REQ-079 | A matched payment updates the invoices it is allocated to | story | a user-visible capability that ships on its own | US-00-019 | AC-US-00-019-1, AC-US-00-019-2, AC-US-00-019-3 |
| REQ-080 | A promise becomes fulfilled when matched payments cover its amount by  | criterion-of US-00-020 | a rule or detail of the capability in US-00-020, tested by its AC, not a separate user action | US-00-020 | AC-US-00-020-1, AC-US-00-020-2, AC-US-00-020-3 |
| REQ-081 | Every state change listed in brief 4.5 writes a TimelineEvent. | story | a user-visible capability that ships on its own | US-00-022 | AC-US-00-022-1, AC-US-00-022-2 |
| REQ-082 | The customer page renders timeline events in time order with icon | criterion-of US-00-022 | a rule or detail of the capability in US-00-022, tested by its AC, not a separate user action | US-00-022 | AC-US-00-022-3 |
| REQ-083 | The dashboard shows total outstanding | story | a user-visible capability that ships on its own | US-00-003 | AC-US-00-003-1 |
| REQ-084 | The dashboard shows ageing buckets 0 to 30 | criterion-of US-00-003 | a rule or detail of the capability in US-00-003, tested by its AC, not a separate user action | US-00-003 | AC-US-00-003-2 |
| REQ-085 | The dashboard shows "What needs my attention today?" grouping high-pri | criterion-of US-00-003 | a rule or detail of the capability in US-00-003, tested by its AC, not a separate user action | US-00-003 | AC-US-00-003-3, AC-US-00-003-4 |
| REQ-086 | The customer detail page shows info | story | a user-visible capability that ships on its own | US-00-004 | AC-US-00-004-1 |
| REQ-087 | The customer detail page shows a recommended next action. | criterion-of US-00-004 | a rule or detail of the capability in US-00-004, tested by its AC, not a separate user action | US-00-004 | AC-US-00-004-2, AC-US-00-004-3 |
| REQ-088 | A demo payment link page | story | a user-visible capability that ships on its own | US-03-004 | AC-US-03-004-1, AC-US-03-004-2 |
| REQ-089 | A CRM list shows each customer's name | story | a user-visible capability that ships on its own | US-00-026 | AC-US-00-026-1 |
| REQ-090 | Prepare Call shows a summary | criterion-of US-00-025 | a rule or detail of the capability in US-00-025, tested by its AC, not a separate user action | US-00-025 | AC-US-00-025-1 |
| REQ-091 | The autonomy mode is Manual (default) | story | a user-visible capability that ships on its own | US-01-016 | AC-US-01-016-1, AC-US-01-016-2, AC-US-01-016-3 |
| REQ-092 | WhatsApp | criterion-of US-01-016 | a rule or detail of the capability in US-01-016, tested by its AC, not a separate user action | US-01-016 | AC-US-01-016-4 |
| REQ-093 | Every model call goes through one gateway function that calls OpenRout | story | a user-visible capability that ships on its own | US-01-008 | AC-US-01-008-1 |
| REQ-094 | The gateway caps `max_tokens` at 500. | criterion-of US-01-008 | a rule or detail of the capability in US-01-008, tested by its AC, not a separate user action | US-01-008 | AC-US-01-008-2 |
| REQ-095 | The gateway logs tokens and cost per call and keeps a running total. | criterion-of US-01-009 | a rule or detail of the capability in US-01-009, tested by its AC, not a separate user action | US-01-009 | AC-US-01-009-1, AC-US-01-009-2, AC-US-01-009-4 |
| REQ-096 | The gateway refuses calls once the budget is exhausted and logs a Guar | criterion-of US-01-009 | a rule or detail of the capability in US-01-009, tested by its AC, not a separate user action | US-01-009 | AC-US-01-009-3 |
| REQ-097 | The gateway retries with backoff and enforces timeouts. | criterion-of US-01-008 | a rule or detail of the capability in US-01-008, tested by its AC, not a separate user action | US-01-008 | AC-US-01-008-3 |
| REQ-098 | The gateway runs in `live` | criterion-of US-01-008 | a rule or detail of the capability in US-01-008, tested by its AC, not a separate user action | US-01-008 | AC-US-01-008-4, AC-US-01-008-5 |
| REQ-099 | With the kill switch on | story | a user-visible capability that ships on its own | US-01-002 | AC-US-01-002-1, AC-US-01-002-2, AC-US-01-002-3 |
| REQ-100 | An admin toggles sending and autonomy mode and views status | criterion-of US-01-006 | a rule or detail of the capability in US-01-006, tested by its AC, not a separate user action | US-01-006 | AC-US-01-006-2, AC-US-01-006-3 |
| REQ-101 | An evaluation over 40 labelled replies reports classification accuracy | story | a user-visible capability that ships on its own | US-01-010 | AC-US-01-010-1 |
| REQ-102 | At least 10 trajectory scenarios (input | story | a user-visible capability that ships on its own | US-01-011 | AC-US-01-011-1, AC-US-01-011-2 |
| REQ-103 | Every draft in the guardrail red-team set (invented amounts | story | a user-visible capability that ships on its own | US-01-012 | AC-US-01-012-1, AC-US-01-012-2 |
| REQ-104 | Evaluation results are written to `docs/evals/report.md` and shown on  | criterion-of US-01-010 | a rule or detail of the capability in US-01-010, tested by its AC, not a separate user action | US-01-010 | AC-US-01-010-2 |
| REQ-105 | CI runs the evaluation in replay mode. | criterion-of US-01-010 | a rule or detail of the capability in US-01-010, tested by its AC, not a separate user action | US-01-010 | AC-US-01-010-3 |
| REQ-106 | The test suite passes with no OpenRouter key | story | a user-visible capability that ships on its own | US-01-013 | AC-US-01-013-3 |
| REQ-107 | `docker compose up` from a clean checkout with only Docker installed s | criterion-of US-01-013 | a rule or detail of the capability in US-01-013, tested by its AC, not a separate user action | US-01-013 | AC-US-01-013-1 |
| REQ-108 | The Makefile provides `up` | criterion-of US-01-013 | a rule or detail of the capability in US-01-013, tested by its AC, not a separate user action | US-01-013 | AC-US-01-013-2 |
| REQ-109 | The README contains How to run | story | a user-visible capability that ships on its own | US-01-015 | AC-US-01-015-1, AC-US-01-015-2, AC-US-01-015-3 |
| REQ-110 | The ABC Distributors story in brief 4.24 runs end to end: selection wi | criterion-of US-01-005 | a rule or detail of the capability in US-01-005, tested by its AC, not a separate user action | US-01-005 | AC-US-01-005-3, AC-US-01-005-4 |
| REQ-111 | Users sign in with one of three roles | story | a user-visible capability that ships on its own | US-01-007 | AC-US-01-007-1, AC-US-01-007-2, AC-US-01-007-3 |
| REQ-112 | The api exposes `/healthz` and `/readyz`. | story | a user-visible capability that ships on its own | US-01-014 | AC-US-01-014-1 |
| REQ-113 | Logs are structured JSON and contain no PII message bodies. | criterion-of US-01-014 | a rule or detail of the capability in US-01-014, tested by its AC, not a separate user action | US-01-014 | AC-US-01-014-2 |
| REQ-114 | Dates display in Indian format (`05 Oct 2026`). | criterion-of US-00-023 | a rule or detail of the capability in US-00-023, tested by its AC, not a separate user action | US-00-023 | AC-US-00-023-3 |
| REQ-115 | The UI offers light and dark themes. | criterion-of US-00-023 | a rule or detail of the capability in US-00-023, tested by its AC, not a separate user action | US-00-023 | AC-US-00-023-4 |
| REQ-116 | The inbound bank-feed webhook verifies a signature and rejects request | criterion-of US-00-017 | a rule or detail of the capability in US-00-017, tested by its AC, not a separate user action | US-00-017 | AC-US-00-017-3, AC-US-00-017-4 |
| REQ-117 | The daily collection run and the promise check run as scheduled jobs. | criterion-of US-01-001 | a rule or detail of the capability in US-01-001, tested by its AC, not a separate user action | US-01-001 | AC-US-01-001-7 |
| REQ-118 | A missed promise produces a recommended follow-up. | criterion-of US-00-020 | a rule or detail of the capability in US-00-020, tested by its AC, not a separate user action | US-00-020 | AC-US-00-020-4 |
| REQ-119 | A statement request produces a recommended action to send a statement  | story | a user-visible capability that ships on its own | US-00-015 | AC-US-00-015-1, AC-US-00-015-2 |
| REQ-120 | The system counts `OPENROUTER_API_KEY` as a secret: it is never commit | criterion-of US-01-013 | a rule or detail of the capability in US-01-013, tested by its AC, not a separate user action | US-01-013 | AC-US-01-013-4 |

## Gaps

| REQ | Why uncovered | Proposed action |
| --- | --- | --- |
| none | | |

## Orphan stories

| Story | Reason it exists | Action |
| --- | --- | --- |
| none | | |

## Counts

stories-coverage: 120 REQ from docs/product/PRD.md (0 withdrawn), 120 covered, 0 out of scope, 0 gaps, 46 stories, 161 AC, 0 orphans, 0 problems
Verdict: covered
