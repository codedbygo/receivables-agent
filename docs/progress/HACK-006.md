# Progress: HACK-006 Demo readiness, hosted demo fix and 10-customer seed

- Task: HACK-006
- Title: Demo readiness, hosted demo fix and 10-customer seed
- Branch: main (at the engineer's request; no task branch)
- Status: committed (1188951) and deployed; hosted reset ran (smoke reset passed); the count of 10 is not yet confirmed
- Owner: Savitha Sista
- Started: 2026-10-07
- Updated: 2026-10-07
- Acceptance criteria: 10 seeded customers on every reset; every eval scenario still passes

## Next
- Engineer: commit (leave AGENTS.md out), push main, deploy to Vercel, then Admin, Reset demo data once on the hosted demo
- Engineer: approve the ABC draft on the hosted demo and confirm the email reaches the EMAIL_REDIRECT_TO inbox
- Engineer, after the demo: rotate the Neon collections_owner password and the three access codes (both were pasted into a chat session)
- Add `alembic upgrade head` against Neon to the Vercel deploy steps in docs/environments.md (nothing runs migrations there)

## Done
- Demo readiness on main at 733060d: make check passed (6 gates, 0 skipped); 631 tests at 100% coverage on PostgreSQL 17; Playwright 28/28; smoke 6/6; make audit clean; 17 live security probes behaved as expected; no Critical or High finding
- Hosted demo: SESSION_SECRET already set; all three access codes regenerated and redeployed; Neon was at migration 0001, so reset and settings returned 500 (portal_links and feature_sms missing); upgraded to 0007; smoke then passed health, reset and dashboard (MCP and Mailpit checks fail by design on Vercel)
- Seed cut from 50 customers, 300 invoices, 40 replies to 10, 60, 20: the 10 customers the demo story and the 12 eval scenarios use; Deccan Polymers now fully paid and Ganesh Traders clean, so every profile still has a customer; dead seed branches removed; smoke accepts up to 15 overdue customers and requires ABC
- REQ-018, AC-US-01-003-1, AC-US-01-003-3 (at least one customer per profile), AC-US-00-002-2, AC-US-00-026-1 and the matching test cases updated
- Verified after the seed change: make check passed; full suite 100.00% coverage; make eval scenarios 12/12 (report changed only its timestamp); Playwright 28/28; smoke 6/6 with MCP top 7
- Notion report written and kept up to date: build report, security, architecture, database, Bearing feedback, role-by-role demo walkthrough

## Blockers
- none

## Decisions
- 10 customers chosen by what the story and scenarios need, not the hand-trimmed ra-livetest set (engineer chose option A, then option 1)

## Links
- MR: none
- Ticket: none
- Report: https://app.notion.com/p/3f2999fd2816815c8f18e3220ace740d
