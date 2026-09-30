# ADR-0011: Move the payment and clock stories into P0

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: scope
- Reversibility: cheap: a priority change

## Context

The estimate found the ABC story (REQ-110, Must) needs US-01-004, US-00-017, US-00-019 and US-00-020, which the brief's order puts in P1; without them P0 demos stop at the promise and dispute.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Move the four stories (11 points) into P0 (chosen) | Must grows from 92 to 103 points | n/a |
| Keep the brief's order | the story would not be complete in P0 | a deadline that cannot fit 103 points |

## Decision

We will build US-01-004, US-00-017, US-00-019 and US-00-020 inside P0, because the brief marks the whole story as must be flawless.

## Consequences

The backlog priority column is unchanged (Should) so ids and history stay stable; the build order in the estimate and the phase plan carries the change.

## Commits us to

none
