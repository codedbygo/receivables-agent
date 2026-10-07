# ADR-0018: Connect one company Google account for Gmail and Calendar, through the REST APIs

- Status: Accepted
- Date: 2026-10-07
- Task: HACK-009
- Deciders: Savitha Sista (engineer)
- Area: integrations, email, security
- Reversibility: cheap (EMAIL_PROVIDER=smtp, Disconnect on the Admin page)

## Context

Customer replies were typed in by hand (debt D-001), reminders left by SMTP with an app password, and promises
lived only in the console. The engineer asked for Gmail and Google Calendar: send from the company mailbox, read the
customers' replies, and put promises and follow-ups in a calendar.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| One company account over the Gmail and Calendar REST APIs with httpx (chosen) | needs a Google Cloud OAuth client; Testing mode re-consents weekly | a team sharing one collections mailbox |
| Each collector connects their own account | per-user tokens, per-user calendars, more screens | collectors who own their customers |
| IMAP for replies, SMTP for sending, iCal feed for the calendar | app passwords, no thread ids, a feed the calendar polls slowly | a mailbox without Google |
| google-api-python-client | a large new dependency for a handful of REST calls | heavy use of many Google APIs |

## Decision

- An admin presses **Connect Google**; the OAuth code flow (offline access, consent each time so a refresh token
  always comes back) stores the refresh token in `google_account`, encrypted with Fernet under `GOOGLE_TOKEN_KEY`.
  The signed state (HMAC with `SESSION_SECRET`, 10 minutes) is the callback's only credential.
- Scopes: `gmail.send`, `gmail.readonly` and `calendar.events`, plus `openid email` to name the account.
- `EMAIL_PROVIDER=gmail` sends reminders with `users.messages.send`; the thread id is stored on the message.
  The redirect and allow-list rules (ADR-0017) apply unchanged.
- Replies: only threads of reminders sent in the last 60 days are read. A new message not from the account goes to
  `inbound_emails` as pending, with the quoted history cut off; a collector accepts it (stored and classified by the
  existing reply pipeline) or dismisses it.
- Calendar: one all-day event per pending promise and per open follow-up task; removed when settled or closed.
  The ledger is the source and every sync can be repeated.
- A `google_sync` job runs every 5 minutes while connected (worker loop; on Vercel, the cron tick), plus
  **Sync now** and **Check for replies** buttons. A demo reset keeps the connection.
- `cryptography` is declared directly (it was already installed through pyjwt) for the encryption.

## Consequences

- In Testing mode Google expires the grant after 7 days; connect again weekly, or publish the app (reading Gmail
  then needs Google's restricted-scope verification).
- Vercel's free cron runs once a day: use the buttons, or an external timer calling `/api/v1/cron/tick` with the
  `CRON_SECRET` bearer every 5 minutes.
- A demo reset drops `calendar_events` rows but not the Google events they pointed to; delete those in the
  calendar after a reset.
- Customer replies, which may hold personal data, are now read from a mailbox and stored; they were already stored
  when pasted.
