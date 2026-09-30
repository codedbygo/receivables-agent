# Debt register

Updated: 2026-09-30. Seeded from the Phase 2 reviews (the repository has no code yet, so no markers, suppressions or skipped tests to harvest). Ranked by cost of carrying.

| Id | Debt | Interest (cost of carrying) | Principal (cost to fix) | Trigger to pay | Owner | Source |
| --- | --- | --- | --- | --- | --- | --- |
| D-001 | Customer replies enter through a simulate action, not a real inbound channel | Every real deployment needs it; demo must say "simulated" | M: inbound SMTP or IMAP poll, parsing, threading | first real pilot | unassigned | CEO review E6, Q-007 |
| D-002 | Ledger is seeded, not synced from an accounting system | No real use without it | L: Tally or Zoho connector | first real pilot | unassigned | PRD non-goal, Q-017 |
| D-003 | "AI cost vs amount collected" dashboard tile deferred | Weaker cost story for judges | S | P1 done with time left | unassigned | CEO review E4 |
| D-004 | Drafts and replies in English only | Excludes regional-language customers | L: parser and tone lexicon per language | customer demand | unassigned | CEO review E5, Q-018 |
| D-005 | Trusted-mode allow-list is a policy file, not admin-editable | Changing it needs a deploy | S | Trusted mode used beyond the demo | unassigned | Q-008 |
