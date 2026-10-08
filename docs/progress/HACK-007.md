# Progress: HACK-007 Manage distributors and invoices

- Task: HACK-007
- Title: Create, edit and delete distributors, add invoices, CSV upload, real-mail allow-list
- Branch: main (at the engineer's request; no task branch)
- Status: built and verified locally, uncommitted
- Owner: Savitha Sista
- Started: 2026-10-07
- Updated: 2026-10-07
- Acceptance criteria: REQ-121 to REQ-125 in docs/product/PRD.md

## Next
- Engineer: commit, push main
- Engineer: migrate Neon to 0008 BEFORE deploying (docs/environments.md, "migrate before every deploy"), then deploy
- Engineer, optional: set EMAIL_ALLOW_REAL in Vercel to your own test inbox(es) and redeploy, to receive a real reminder

## Done
- API: POST /customers, PATCH /customers/{id}, DELETE /customers/{id} (admin only), POST /customers/{id}/invoices,
  POST /customers/import (CSV, all or nothing, 500 rows, 1 MB); api/openapi.yaml updated
- Migration 0008: timeline kinds customer_created, customer_updated, invoice_added (round-tripped 0008 to 0007 to 0008)
- Delete removes the customer's queued send jobs, follow-ups, calls, escalations, disputes, promises, replies,
  messages, allocations, payments, invoices and runs in one transaction; notes, portal links and timeline cascade
- EMAIL_ALLOW_REAL: listed addresses get real mail, everything else still goes to EMAIL_REDIRECT_TO
- Console: Add distributor, Upload CSV and Delete on Customers; Edit details, Add invoice and Delete on the customer
  page; FastAPI's own 422 bodies now show each field's reason instead of "The server did not answer as expected"
- Found and fixed while testing: a name of only spaces passed validation and hit the database constraint (a 500)
- Verified: make check passed (6 gates, 0 skipped; 282 unit, 26 console); full suite 100.00% coverage on PostgreSQL 17;
  Playwright 32/32 (one earlier run failed the demo story's 60 s wait for a send right after stack start, then passed
  three times)

## Blockers
- none

## Decisions
- Delete is admin-only; create, edit, invoice and upload are collector and admin
- An upload never edits a known customer's details; it only adds the invoice
- Reset is unchanged: it drops added distributors and restores the 10 seeded ones
- The service was written before its tests (the testing rule asks for test first); every behaviour has a test now

## Links
- MR: none
- Ticket: none
- Report: https://app.notion.com/p/3f2999fd2816815c8f18e3220ace740d
