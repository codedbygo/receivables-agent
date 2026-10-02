# ADR-0014: Serve the hosted demo over HTTPS with a Caddy container

- Status: Accepted
- Date: 2026-10-02
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved adding Caddy on 2026-10-02)
- Area: deployment
- Reversibility: cheap

## Context

ADR-0013 moved sign-in to access codes sent as Bearer tokens. On a public host those codes must never cross
plain HTTP. The compose stack had no TLS: nginx served the console on port 80 inside the network and
127.0.0.1:8080 on the host.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Caddy container in compose.prod.yaml (chosen) | one more image | a single host with its own DNS name |
| TLS in nginx with certbot | certificate renewal is a second process to run and watch | teams already running certbot |
| The host's or cloud's load balancer | not every demo host has one | a managed platform |

## Decision

compose.prod.yaml adds `caddy:2.10-alpine` running `caddy reverse-proxy --from $PUBLIC_HOST --to web:80`.
It is the only service published on a public interface (80 and 443); it obtains and renews the certificate
itself and keeps it in the `caddy_data` volume.

## Consequences

DNS for `PUBLIC_HOST` must point at the host before the first start, and ports 80 and 443 must be open.
Locally nothing changes: the base compose.yaml has no Caddy.

## Commits us to

Pinning the Caddy image like the others; `make audit` does not scan images, so image updates are manual.
