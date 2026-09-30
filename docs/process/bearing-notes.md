# Bearing rules and gates for HACK-001

Source: `~/bearing/docs/WORKFLOW.md`, `docs/REPO_LAYOUT.md` (kit 0.6.0, read 2026-09-30). The handbook sites need JavaScript; the repository docs are the same content.

## Rules that bind this project

| Rule | What it means here |
| --- | --- |
| Engineer pushes, merges, tags, deploys | Claude prints `git push`, `docker push`, tag and deploy commands; never runs them. |
| One task per branch | Work stays on `main` at the engineer's request (2026-09-30); no task branch. |
| `make` is the only entry point | CI jobs call make targets only. `make check` is the gate and prints `check: R gates run, S skipped`; any skip fails unless `BEARING_ALLOW_SKIP=1` locally. |
| commit-msg hook | Conventional Commit subject, task id (`HACK-001`) in the message, no AI trailer, no em dash. |
| pre-commit hook | format, lint, secret scan (gitleaks) on staged files. |
| pre-push hook | no push to trunk, branch name shape, `make check`. |
| Secrets | `.env` is never committed and never read by the agent. `.env.example` lists every variable. |
| Scratch | Temporary files in `.scratch/` (ignored). Session state in `.bearing/state/` (ignored). Shared progress in `docs/progress/HACK-001.md` (committed). |
| Reports | Shape: Changed, Verified, Not done, Noticed. "not run" for anything not run. |
| Tracker | `BEARING_TRACKER=none`: `tracker-sync` rows skip with a note. |
| Prose | No em dashes, no AI attribution in commits, MRs or docs. |

## Gates per phase (from the master prompt, mapped to skills)

| Gate | Pass condition | Checked by |
| --- | --- | --- |
| 1 Discover | Every brief item maps to a REQ; every P0 REQ has a story with testable ACs | `backlog` coverage matrix |
| 2 Plan | P0 completable alone; CEO and eng findings applied or in `docs/DEBT.md` | `estimate`, `/plan-ceo-review`, `/plan-eng-review` |
| 3 Choose | One ADR per open choice; single decision checkpoint | `tech-decision`, `adr` |
| 4 Architecture | HLD, LLD, ERD, OpenAPI, threat model exist; spec drift 0; every P0 REQ has an HLD component | `openapi-spec`, `high-level-design` critic |
| 7 Repo | `make check` green with 0 skips | `gate-audit` |
| 9 Verify | Traceability 0 gaps; DoD verdict with evidence | `traceability`, `definition-of-done` |

## Hackathon depth

Full: office-hours, plan-ceo-review, prd, backlog, plan-eng-review, tech-decision/adr, HLD, LLD, data-model, threat-model, llm-agent, mcp-server, llm-guardrails, llm-gateway, llm-eval, test-cases, TDD, definition-of-done, branch-review, traceability, verify-deploy.
Lightweight (one page): estimate, openapi-spec, auth, background-jobs, webhooks, deployment-architecture, ux-flows, design-system, observability, privacy-review.
Skipped: load-test, resilience-testing, api-versioning, i18n, analytics-events, ab-experiment, cloud-cost, on-call, vapt-report, client-deliverables, autopilot.

## Repository facts at start

- No commits; `origin` (github.com:codedbygo/receivables-agent) is empty. Work is committed on `main`; the engineer pushes.
- Git host: GitHub (from the remote), so the GitHub CI and PR template set applies.

## Deviations recorded

- GSD `gsd-plan-phase` (Phase 2) is deferred to the start of Phase 8, after the stack is fixed: `.planning/` needs `gsd-new-project` first and its phase files would name modules that do not exist until Phase 3 and 4 decide them.
- `tracker-sync` skipped: `BEARING_TRACKER=none`.
- Gstack review skills ran with recommended options auto-taken under the master prompt's pause policy; every auto-decision is listed at the Phase 3 checkpoint.
