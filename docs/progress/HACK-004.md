# Progress: HACK-004 Fix the 15 issues from the manual end-to-end QA of 2026-10-06, then make CI pass

- Task: HACK-004
- Title: Fix the 15 issues from the manual end-to-end QA of 2026-10-06, then make CI pass
- Branch: fix-amount-issue (created by the engineer from main at d09d865)
- Status: in review
- Owner: Savitha Sista
- Started: 2026-10-06
- Updated: 2026-10-07
- Acceptance criteria: none

## Next
- address review comments

## Done
- High: drafts are re-checked against the ledger at approval and in the send gate; a draft made stale by a payment goes back to the queue unverified (ISSUE-011, tenet 4 updated)
- Medium: portal refuses "-500" and keeps decimals (006); one credit settles one promise across checks (009); the preferences dialog starts from stored consent (014); "ignore your instructions" is flagged on calls and replies (012); batch approval asks for confirmation (010); the Customers list shows the real next action (001) and the business-date last contact (002); every page fits 390px (005)
- Low: plain email casing (004); customers see messages without error codes (007); rate disputes are price disputes (008); "never contacted" only when nothing was sent (013); Home and End on the sidebar handle (015); "Not prioritised" at score 0 (003)
- CI: a reply during a running agent run now waits for it instead of a 422 (the flaky demo e2e); the stale voice e2e test opens the right tab; tests added to 100% coverage, including the signed Twilio webhooks
- Verified 2026-10-07: make check passed (280 unit); coverage 100% overall and core (631 tests on PostgreSQL 17); make eval scenarios 12/12; make audit clean; Playwright 28/28 three times; red proof for every regression test; smoke 147 requests, 0 failed

## Blockers
- none (pushing, merging and history rewrites are the engineer's)

## Decisions
- none

## Links
- MR: none
- Ticket: none
