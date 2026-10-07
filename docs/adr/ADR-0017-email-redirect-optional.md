# ADR-0017: The email redirect inbox is optional; with none set, customers are mailed directly

- Status: Accepted
- Date: 2026-10-07
- Task: HACK-008
- Deciders: Savitha Sista (engineer)
- Area: email, safety
- Reversibility: cheap (restore the startup check in app/channels/email.py)

## Context

Since the hosted demo was set up, the API refused to start with real SMTP (`SMTP_USER` set) unless
`EMAIL_REDIRECT_TO` named one inbox to receive every message. The rule protected the seeded demo customers, whose
made-up addresses (`accounts@<name>.example.in`) must never receive mail. The engineer now runs the hosted system
with real distributors and their real addresses, and wants each reminder to reach its customer.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Redirect optional, empty means mail the customer (chosen) | the seeded customers are mailed too if a reset brings them back | a system whose customers are real |
| Keep the redirect required and list real addresses in `EMAIL_ALLOW_REAL` | every new distributor needs a settings change and a redeploy | a demo with a few real test inboxes |
| Allow whole domains in `EMAIL_ALLOW_REAL` | still a redirect to maintain | a demo mixing fake and real customers |

## Decision

`EMAIL_REDIRECT_TO` is optional. When it is set, every message goes there except the addresses in
`EMAIL_ALLOW_REAL` (unchanged). When it is empty, every message goes to the customer's own address. The startup
check that refused real SMTP without a redirect is removed.

## Consequences

- Approving a reminder now sends real email to the customer named on it. The human approval and the ledger
  checks at approval and at send time are unchanged.
- **Demo reset reseeds 10 customers with `@...example.in` addresses.** With no redirect set, approving one of their
  reminders mails that domain. On a system with real customers, do not use Admin, Reset demo data, or set
  `EMAIL_REDIRECT_TO` while demoing with the seed.
