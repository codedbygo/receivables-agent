# ADR-0003: Use PostgreSQL 17 with Alembic migrations

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: database
- Reversibility: awkward: data and migrations are Postgres-specific (views, SKIP LOCKED)

## Context

The brief fixes Postgres (brief, sections 5 and 6). postgres:16-alpine and 17-alpine are both cached locally.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| PostgreSQL 17 (postgres:17-alpine) (chosen) | none material | n/a |
| PostgreSQL 16 | older; no reason to prefer | an existing 16 fleet |
| PostgreSQL 18 (cached, 650 MB image) | larger image, newest major | a need for 18 features |

## Decision

We will use PostgreSQL 17 from the cached postgres:17-alpine image, with Alembic migrations that each carry a tested downgrade, because the brief fixes Postgres and 17 is current and already on the machine.

## Consequences

Money is BIGINT paise with CHECK constraints on status enums; derived balances come from a view (eng review A6).

## Commits us to

PostgreSQL 17, Alembic
