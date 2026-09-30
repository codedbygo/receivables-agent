# ADR-0006: Use a Postgres job table with SKIP LOCKED for background work

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: jobs
- Reversibility: cheap: jobs are rows; moving to a broker changes the worker only

## Context

The daily run, promise check and send worker need scheduling, retries and idempotency (brief, section 6). Adding Redis or a broker adds a service on a slow machine.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Postgres jobs table, SELECT FOR UPDATE SKIP LOCKED, unique (kind, run_date) (chosen) | polling every 2 s | n/a |
| Celery + Redis | extra service and dependency | high job volume |
| APScheduler in-process | no durable queue or idempotency across restarts | a single process with no send queue |

## Decision

We will use a Postgres jobs table polled by the worker with SKIP LOCKED, with unique keys per run date and per message, because it needs no new service and makes idempotency a database constraint (eng review A5).

## Consequences

Revisit above about 50 jobs per second.

## Commits us to

PostgreSQL (ADR-0003)
