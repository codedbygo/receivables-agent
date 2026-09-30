# Estimate: AI Receivables Collections Agent

Backlog: docs/product/backlog.md (46 stories, 161 AC)   Estimated: 2026-09-30   Scale: XS 1, S 2, M 3, L 5, XL 8

## Answer

**Verdict: not decidable yet.** Remaining work is 137 points (Must 92, Should 31, Could 14). No sprint log exists and the hackathon deadline is not in the repository, so capacity is `unconfirmed:`. The deadline is asked at the Phase 3 checkpoint; with it, the fit check is one line of arithmetic below.

- Remaining: 46 sized, 0 refused (every story has AC), 0 done or withdrawn.
- Velocity: unconfirmed: no sprint log. Team: unconfirmed: 1 engineer driving Claude Code.
- Calendar: no leave or holidays known; no freeze date known.

## Points by tier

| Tier | Stories | Points | Largest (L = 5) |
| --- | --- | --- | --- |
| Must (P0) | 29 | 92 | US-01-001 agent run, US-00-006 fact guardrails, US-00-012 classification, US-01-005 ABC reset + e2e, US-01-008 gateway, US-03-002 MCP core tools, US-01-013 compose + make |
| Should (P1) | 12 | 31 | none above M |
| Could (P2) | 5 | 14 | none above M |
| Total | 46 | 137 | no XL; nothing to split |

Drivers behind the L stories: new boundary plus schema (US-01-013, US-03-002), third-party integration (US-01-008 OpenRouter), more than four AC (US-01-001 seven, US-00-006 six, US-00-012 five), and the end-to-end story test (US-01-005).

## Phase plan (each phase leaves something demonstrable)

| Phase | Stories | Points | What a user can do at the end |
| --- | --- | --- | --- |
| P0-a Foundation | US-01-013, US-01-003, US-00-001, US-00-023, US-01-008, US-01-009 | 20 | `docker compose up`, seeded ledger, invoice lists in ₹, gateway in replay |
| P0-b Draft path | US-00-002, US-03-002, US-01-001, US-00-005, US-00-006, US-00-007, US-00-008 | 26 | daily run produces verified drafts with a readable trajectory |
| P0-c Send and reply | US-00-009, US-00-010, US-00-011, US-03-001, US-00-012, US-00-013, US-00-014, US-00-016 | 22 | approve, send to MailHog, reply becomes a promise or an escalated dispute |
| P0-d Story and proof | US-00-022, US-00-003, US-00-004, US-01-005, US-01-010, US-01-011, US-01-012, US-01-015 | 24 | dashboard, timeline, `make demo`, evals, README; the ABC story runs to the dispute beat |
| P1 | US-00-019, US-00-017, US-00-018, US-00-020, US-00-021, US-01-004, US-01-002, US-01-006, US-01-007, US-01-014, US-00-015, US-03-003 | 31 | payment, clock and promise-fulfilled beats; kill switch; admin; roles |
| P2 (flagged) | US-00-024, US-00-025, US-03-004, US-00-026, US-01-016 | 14 | WhatsApp, Prepare Call, payment link, CRM list, autonomy modes |

## Gap found: the ABC story is not P0-complete on its own

REQ-110 (Must, in US-01-005) walks the story through "advance demo clock", "bank payment auto-matched", "outstanding ₹4,50,000" and "promise fulfilled". Those beats are delivered by US-01-004, US-00-017, US-00-019 and US-00-020, which the brief's build order puts in P1. So P0 alone demos the story only up to the promise and the dispute. Gate 2 asks for a P0 that is completable on its own.

Proposed (for Phase 3, not applied): either (a) move US-01-004, US-00-017, US-00-019 and US-00-020 (11 points) into P0, making Must 103 points; or (b) keep the brief's order and state that P0's demo ends at the promise and dispute, with AC-US-01-005-3 split so the payment beats move to P1. Recommendation: (a), because "must be flawless" is written on the whole story, and the brief's own P1 list is ordered by build, not by demo need.

## Assumptions that would change sizes

- MCP SDK 2.x works as the spike showed (docs/spikes/2026-09-30-mcp-python-transports.md); a regression adds 2 points to US-03-002.
- Stack is the brief's default (FastAPI + Next.js). A single Python app with server-rendered pages would cut roughly 10 to 15 points of UI and build plumbing; decided in Phase 3. unconfirmed:
- Slow network on the build machine (docs/spikes/2026-09-30-mail-catcher.md) adds wall-clock time to US-01-013 that points do not show.

## Fit check, once the deadline is known

capacity = points per day x working days to freeze. For a reference only (unconfirmed:): at 15 points per day, Must (92) takes about 6 days, Must plus Should (123) about 8, all (137) about 9. Cut order if it does not fit: Could (US-01-016, US-00-024, US-00-025, US-03-004, US-00-026), then Should that the story does not need (US-01-007, US-01-014, US-00-015, US-03-003).

Tasks: 0 tasks: hours not estimated.
