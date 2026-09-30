# ADR-0001: Use Python FastAPI with SQLAlchemy and Alembic for the backend

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: backend
- Reversibility: awkward: every service module is Python; a rewrite costs the backend

## Context

The repository is empty. The brief proposes Python FastAPI + SQLAlchemy + Alembic as the default (docs/product/brief.md, section 0). The MCP spike ran on Python 3.12 with mcp 2.2.0 (docs/spikes/2026-09-30-mcp-python-transports.md). This machine runs Python 3.12.3; no Python image is cached and the network is slow.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, uv (chosen) | Bearing's Python rules name 3.14; 3.12 is kept to match the machine and one slim base image | n/a |
| Node 24, Fastify, Drizzle | second language for the MCP work already proven in Python | a team that is TypeScript-only |

## Decision

We will build api, mcp and worker as one Python 3.12 package on FastAPI, SQLAlchemy 2 and Alembic, managed with uv, because the brief names it, the MCP spike proved it here, and one language keeps the service layer single (eng review A1, A2).

## Consequences

One backend image with three entrypoints. Revisit the Python version when the base image is cached and Bearing's 3.14 rules matter more than download time.

## Commits us to

Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, uv, psycopg 3
