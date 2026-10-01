# Progress: HACK-001 CollectionsAgent

- Task: HACK-001
- Title: CollectionsAgent
- Branch: develop
- Status: in progress
- Owner: Savitha Sista
- Started: 2026-09-30
- Updated: 2026-09-30
- Acceptance criteria: 120

## Next
- Engineer: make up and follow README section 2 on a clean clone (not run in the sandbox: no Docker socket)
- Record replay fixtures with a key (D-007); Phase 9 reviews (branch-review, cso, traceability, privacy, licences)

## Done
- Phases 1 to 7: PRD, backlog, reviews, ADRs, HLD, LLD, data model, OpenAPI, threat model, design, genai design, repo scaffold
- P0 backend: schema, seed, ledger, priority, gateway, MCP tools, bounded agent, drafting and guardrails, approval and send, replies, payments and promises
- API layer for every P0 flow; ABC story passes end to end over HTTP (tests/service/test_story_api.py)
- Eval harness: make eval (12/12 scenarios, 18/18 red team, 6/6 golden, replies 39/40) and make eval-replay in make check
- Web console (React 19, Vite, TanStack Query, Tailwind, Zod): Today, Approvals, Customers, Customer, Admin, Evaluation, Pay
- P2 behind flags: Trusted mode, simulated WhatsApp, Prepare Call, SIMULATED payment link
- Phase 9 (2026-10-01): make check 6 gates pass (140 unit, evals red team 23/23); integration passes; privacy review, NOTICE-THIRD-PARTY.md, docs/testing/test-cases.md (161 cases). Reviews fixed with regression tests: model could log promises and name other customers; stuck 'running' agent runs; one credit fulfilling two promises; dates/amounts the verifier missed and payment-detail redirection; edit skipped subject, disputes and promises; role matrix; log parameters; webhook signature TypeError; fullwidth injection text. Open findings: D-012, D-013.
- Playwright: ABC story, Evaluation page, P2 flows pass in a browser against the real API, worker and Postgres
- README (6 sections), docs/runbooks/demo-day.md, OpenAPI regenerated with a drift test (0)

## Blockers
- none

## Decisions
- none

## Links
- MR: none
- Ticket: none
