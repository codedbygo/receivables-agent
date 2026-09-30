# ADR-0010: Deploy with local Docker Compose only

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: hosting
- Reversibility: cheap

## Context

The brief makes local Compose mandatory and a hosted demo optional.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Local Docker Compose (chosen) | judges must run it locally or watch a local demo | n/a |
| Single VM with a production override | needs a host, secrets and basic auth for Mailpit | a remote judging format |

## Decision

We will ship local Docker Compose with six services (postgres, mailhog, api, mcp, worker, web); a hosted demo is a separate later decision.

## Consequences

The engineer runs every push and deploy.

## Commits us to

Docker Compose
