# ADR-0015: Host the console on Vercel; keep the backend on a compose host

- Status: Proposed (the backend host name is not chosen yet)
- Date: 2026-10-02
- Task: HACK-001
- Deciders: Savitha Sista (engineer; asked for a Vercel deployment on 2026-10-02)
- Area: deployment
- Reversibility: cheap

## Context

The engineer asked to deploy on Vercel. The console is a static Vite build with hash routes that calls
`/api/v1/...` on its own origin. The backend is a FastAPI API, a polling worker, an MCP HTTP server, Postgres
and Mailpit: long-running processes and stateful containers, which Vercel's functions do not host.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Console on Vercel, `/api/*` rewritten to the compose host (chosen) | two places to deploy | a public console URL on Vercel's CDN |
| Everything on the compose host behind Caddy (ADR-0014) | no Vercel | one host, one deploy |
| Backend as Vercel functions | the worker, MCP server, Postgres and Mailpit cannot run there | a stateless API only |

## Decision

`frontend/vercel.json` builds the console (`pnpm run build`, output `dist`), sends the same security headers as
nginx, and rewrites `/api/:path*` to `https://<API host>/api/:path*`. The API host is the compose host from
docs/environments.md (compose.prod.yaml with Caddy), its `PUBLIC_HOST`. The browser stays on one origin, so
there is no CORS and the access code travels over HTTPS on both hops.

## Consequences

`REPLACE_WITH_API_HOST` in vercel.json must be set before the first Vercel deploy (Vercel does not expand
environment variables in rewrites). "Run agent now" can take up to 90 s; check the Vercel proxy's timeout for
external rewrites on the chosen plan before the demo. The compose host still serves its own console too.

## Commits us to

Deploying the backend first, then the console; rolling back each on its own.
