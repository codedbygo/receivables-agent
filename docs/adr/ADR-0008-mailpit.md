# ADR-0008: Use Mailpit as the SMTP test inbox

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: mail
- Reversibility: cheap: one image line

## Context

The brief names MailHog (SMTP 1025, UI 8025). The spike found mailhog/mailhog last pushed 2020-08-11 (145 MB) and axllent/mailpit pushed 2026-09-27 (13.7 MB), same ports; a Mailpit copy is cached.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Mailpit, compose service still named mailhog (chosen) | name differs from the brief; docs say MailHog-compatible | n/a |
| MailHog | unmaintained since 2020, 145 MB on a slow link | judges who require the MailHog image by name |

## Decision

We will run Mailpit on ports 1025 and 8025 under the compose service name mailhog, because it is maintained, small and already cached; application code only speaks SMTP.

## Consequences

E2E tests read messages through Mailpit's /api/v1/messages.

## Commits us to

Mailpit
