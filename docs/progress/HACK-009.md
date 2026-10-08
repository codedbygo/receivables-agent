# Progress: HACK-009 Connect Gmail and Google Calendar

- Task: HACK-009
- Title: One company Google account: Gmail sending, incoming replies with a review queue, Calendar sync
- Branch: main (at the engineer's request; no task branch)
- Status: built and verified locally against a faked Google; not yet tried against real Google; uncommitted
- Owner: Savitha Sista
- Started: 2026-10-07
- Updated: 2026-10-07
- Acceptance criteria: REQ-126 to REQ-129 in docs/product/PRD.md; decision in ADR-0018

## Next
- Engineer: Google Cloud project, Gmail and Calendar APIs, OAuth consent (External, Testing, company Gmail as
  a test user), OAuth client with the callback URI (README, "Connecting Google")
- Engineer: set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_KEY, GOOGLE_REDIRECT_URI and EMAIL_PROVIDER=gmail
  in Vercel; migrate Neon to 0009; commit, push, deploy; Admin, Connect Google
- First real run: approve a reminder, reply to it from the customer's mailbox, Check for replies, Accept

## Done
- Migration 0009: google_account (encrypted refresh token), messages.provider_ref, inbound_emails, calendar_events,
  job kind google_sync (round-tripped 0009 to 0008 to 0009)
- OAuth connect and callback with a signed 10-minute state; Disconnect revokes the grant best effort
- GmailChannel (EMAIL_PROVIDER=gmail) through users.messages.send; thread id stored; same redirect rules as SMTP
- Inbox: reads only threads of reminders sent in 60 days, skips our own messages, strips quoted history, queues
  pending; Accept runs the existing reply pipeline, Dismiss records nothing
- Calendar: one all-day event per pending promise and open follow-up; removed when settled or closed; repeatable
- google_sync job every 5 minutes while connected; Sync now and Check for replies buttons; reset keeps the connection
- Console: Google panel on Admin, Incoming replies page and sidebar item
- Declared cryptography (already installed via pyjwt); requirements.txt regenerated for Vercel
- Found by tests and fixed: Google being unreachable during the token request gave a 500 instead of GOOGLE_UPSTREAM
- Verified: make check passed (6 gates, 0 skipped); full suite 100.00% coverage on PostgreSQL 17; Playwright 35/35

## Blockers
- none in code; real Google needs the engineer's Cloud project and credentials

## Decisions
- One company account; replies go through a review queue first (engineer's choice)
- REST over httpx, no Google SDK; Testing mode means connecting again every 7 days

## Links
- MR: none
- Ticket: none
