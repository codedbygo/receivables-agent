# ADR-0009: Use seeded users with session cookies and three roles

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: auth
- Reversibility: cheap

## Context

The brief asks for a role matrix of admin, collector and viewer and names ADMIN_TOKEN; there is one business and no SSO requirement (Q-014).

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Seeded users, server session cookie, ADMIN_TOKEN for scripts (chosen) | no SSO | n/a |
| Token only | browser users would paste tokens | an API-only product |

## Decision

We will seed three users, sign them in with a server-side session cookie, and accept ADMIN_TOKEN for scripts, because it gives the role matrix with no external provider.

## Consequences

SESSION_SECRET joins .env.example. Revisit for multi-tenant use.

## Commits us to

none beyond ADR-0001
