# ADR-0013: Sign in with an access code per role; the role header is for a laptop only

- Status: Accepted (browser sign-in superseded by ADR-0019; scripts and laptop mode stand)
- Date: 2026-10-02
- Task: HACK-001
- Deciders: Savitha Sista (engineer; chose a public hosted demo on 2026-10-02 and approved the plan)
- Area: auth
- Reversibility: cheap
- Supersedes in part: ADR-0009 (the session cookie was never built; the build trusted a role header)

## Context

The API accepted `X-Demo-Role: admin` from any caller. That is safe on a laptop and unsafe on any host others
can reach: anyone could reset the demo, read replies and flip the kill switch (security audit finding 1).
`ADMIN_TOKEN` existed in config and nothing read it.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Access code per role as a Bearer token (chosen) | no per-person identity | one shared demo with three roles |
| Session cookie and password users (ADR-0009) | more code, a login store, CSRF handling | real multi-user use |
| Reverse proxy basic auth only | the API itself stays open to anything behind the proxy | a stopgap |

## Decision

`ADMIN_TOKEN`, `COLLECTOR_TOKEN` and `VIEWER_TOKEN` map a Bearer token to a role (constant-time compare; an empty
code disables the role). `DEMO_OPEN_ROLES=true` keeps the role header for a laptop. The API refuses to start when
open roles are on and `ALLOWED_HOSTS` names a public host, or when no sign-in is configured at all. The console
asks for the code and keeps it in sessionStorage.

## Consequences

Audit actions record the seeded demo user for the role, not a person. Codes are shared secrets: rotate them per
demo. Rate limiting on sign-in is nginx `limit_req` only. Revisit for multi-user use.

## Commits us to

Hosted deployments set the three codes and `DEMO_OPEN_ROLES=false` in their environment, never in the repo.
