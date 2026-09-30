# ADR-0002: Use React with Vite served by nginx for the web console

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: frontend
- Reversibility: cheap to awkward: screens are components; moving to Next.js reuses them

## Context

The console is an authenticated operations tool with no SEO or server-rendering need. The brief's default is Next.js/React + Tailwind + a component library. Only nginx:stable-alpine is cached among web images; node images are not, and the network ran at 33 to 77 KiB/s on 2026-09-30.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| React 19 + Vite + TanStack Query + Tailwind, static build served by nginx (chosen) | no server components; the build runs on the host (node 24 installed) so no Node image is pulled | n/a |
| Next.js (brief default) | adds a Node server runtime and a Node image to pull and run | a public, SEO-facing site or server rendering |
| Server-rendered Jinja + HTMX from FastAPI | weaker fit for the dense, interactive console the brief describes | a very small UI |

## Decision

We will build the web console with React 19, Vite, TanStack Query and Tailwind, served as static files by nginx, because it needs no server runtime, avoids a Node image on this network, and matches Bearing's react house rules (eng review A8).

## Consequences

The web image is nginx plus a built `dist/`. API types are generated from api/openapi.yaml. Revisit if a public page with SEO needs appears.

## Commits us to

React 19, Vite, TypeScript, TanStack Query, Tailwind CSS, nginx
