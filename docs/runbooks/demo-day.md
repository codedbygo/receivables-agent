# Runbook: demo day

For whoever runs the Collections Agent demo on a laptop or projector. Every command runs from the repository
root. The click-by-click script is in README.md, section 2.

## Before the audience arrives (10 minutes)

1. `make web-setup web-build` (skip if `web/dist/index.html` exists and nothing changed).
2. `make up`. Wait for the prompt to return; it waits for every health check.
3. `make demo`. Expect `reset-demo: data at the start of the ABC story, demo date 2026-09-30`.
4. Open http://localhost:8080 (sign in as Admin) and http://localhost:8025 (Mailpit) in two tabs.
5. Admin page: "Sending is on", LLM mode as intended (`replay` unless you set a key), feature flags as you
   want them shown.
6. Optional rehearsal: `make e2e` runs the whole story in a headless browser in about 10 seconds, then
   `make demo` again to reset.

## If something goes wrong

| Symptom | Do this | Why it works |
| --- | --- | --- |
| Any screen shows odd figures or a half-finished story | Admin, Reset demo data (or `make demo`) | Reset locks the tables, deletes and reseeds in one transaction; the worker waits |
| A reminder must not go out | Admin, Pause all sending | The send gate refuses every path (API, worker, MCP); drafting continues |
| Mailpit is down; a message shows Failed with SMTP_UNAVAILABLE | `docker compose restart mailhog`, then Resend on the customer page | Sends retry 5 times, then stop as failed; a resend requeues one job |
| Message stuck as approved | `docker compose logs worker --tail=50`; `docker compose restart worker` | A crash mid-send marks it failed (UNCONFIRMED), never sends twice |
| LLM calls fail or the budget is spent (BUDGET_EXHAUSTED) | Set `LLM_MODE=replay` in `.env`, `make up` | Drafts fall back to templates and replies to the rules classifier; the run says so |
| "A run for this customer is already in progress" | Wait a few seconds and press Run agent now again | One active run per customer is enforced |
| The daily run added many drafts after a reset | Expected: the worker queues the daily run for the demo date | Use the ABC row in Approvals; the others can wait |
| Console blank or "Choose a role again" | `curl -s localhost:8000/api/v1/readyz`; if not ok, `docker compose logs api --tail=50` | The console needs the API healthy |

## Rollback

Check out the previous release tag, run `make web-build` and `make up` (it rebuilds the images), then `make demo`
to put the data back at the start of the story.

## After the demo

`make down` keeps the database volume; `docker compose down -v` also deletes it.
