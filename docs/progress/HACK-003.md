# Progress: HACK-003 Collections employee upgrade

- Task: HACK-003
- Title: Collections employee upgrade (voice, omnichannel, memory, priority factors, follow-up, portal, disputes, CFO, AI Safety)
- Branch: develop (at the engineer's request; no task branch)
- Status: built and verified locally (integration, eval, Playwright, axe), uncommitted
- Owner: Savitha Sista
- Started: 2026-10-03
- Updated: 2026-10-05
- Design: docs/design/collections-employee-upgrade.md (section 9 lists where the build differs)

## Next
- Engineer: one make up, make test-integration on the compose stack (PostgreSQL 17; verified here on 16.2, D-015)
- Try the free options for real: Ollama (`ollama pull qwen2.5:7b`, LLM_PROVIDER=ollama) and the Android SMS Gateway app (D-020)
- Commit on develop (the coding session could not commit), then review with bearing:branch-review and /cso --diff
- A Twilio sandbox run before any real SMS or call (D-016)

## Done
- S1 priority factors and Why? panels; S2 CFO view and AI Safety Center
- S3 dispute categories, routing and lifecycle (migration 0002); follow-up tasks and drafts by autonomy mode (0003)
- S4 channel cadence, preferences and consent, SMS and WhatsApp providers (0004); customer memory and notes (0005)
- S5 AI voice calls: provider abstraction, verified script, intents, signed Twilio webhooks (0006)
- S6 customer portal: hashed tokens, allow-listed view, promise, dispute, help, simulated Pay Now (0007)
- Free options: Ollama provider (local open-source LLM), Android SMS Gateway channel (free SMS), browser Web Speech voice on simulated calls
- Verified 2026-10-05: 260 unit, 311 integration (every file, PostgreSQL 16.2), eval scenarios 12/12, Playwright 24/24 twice, axe AA for CFO view and AI Safety in both themes
- Bugs found by those runs and fixed: recall placeholder dropped by drafting; refused-edit logging deadlock; channel flag read after sending; channel plan 500 for an unknown customer

## Blockers
- none (commits on develop are refused in the coding session; the engineer commits)

## Decisions
- No new dependencies; priority formula unchanged; calls never recorded; follow-ups never auto-sent

## Links
- MR: none
- Ticket: none
