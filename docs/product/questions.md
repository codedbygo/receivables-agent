# Open questions: AI Receivables Collections Agent

PRD: docs/product/PRD.md   Updated: 2026-09-30
Entries: 23   Open: 23   Needs your confirmation: 18

Basis, for every entry:
- stated: the input answers it elsewhere; the passage that wins is named.
- inferred: only one reading is consistent with the rest of the input.
- convention: the input is silent and the team's standards settle it.
- assumption: nothing settles it; a choice was made so the team is not blocked.

## Needs your confirmation

- Q-001 What confidence counts as low for a reply classification? Assumed: below 0.75 goes to human review. (US-00-012)
- Q-002 What weights and band cut-offs does the priority score use? Assumed: weights fixed in the LLD (docs/design/collections-lld.md section 3.2); score 0 to 100; HIGH at 60 and above, MEDIUM 35 to 59, LOW below 35 (changed 2026-09-30 from 70/40 because 70 put ABC Distributors, the brief's HIGH example, in MEDIUM). (US-00-002)
- Q-003 What counts as a payment match? Assumed: exact amount, or reference naming an invoice, within 7 days of the claimed or promised date; exactly one candidate auto-matches. (US-00-017, US-00-018)
- Q-004 When is a promise fulfilled, partially fulfilled or missed? Assumed: payments matched to the customer between the promise's creation and the end of its date cover the amount: fulfilled; cover some: partially_fulfilled; none by the day after: missed. No grace days. (US-00-020)
- Q-005 What does "never argue with the customer" allow? Assumed: on a dispute the system sends nothing automatically; it may draft one fixed acknowledgement ("we have noted your concern and a team member will contact you"), which still needs approval. (US-00-016)
- Q-006 Which legal wording has the business configured? Assumed: none; the policy file holds an allow-list that is empty by default, so any legal-action wording is rejected. (US-00-007)
- Q-007 How does a customer reply reach the system? Assumed: MailHog has no inbound path, so replies enter through a "Simulate customer reply" action (UI and API) and the seed's 40 replies. (US-03-001)
- Q-008 What is allow-listed under Trusted mode? Assumed: gentle tone, email channel, LOW or MEDIUM band, no open dispute, no missed promise, total cited at most ₹1,00,000. (US-01-016)
- Q-009 What does Assisted mode's batch approval do? Assumed: one action approves every pending draft that passed guardrails in the current run; each can still be rejected singly first. (US-01-016)
- Q-010 When do the daily run and promise check run? Assumed: a scheduled daily run at 09:00 IST plus a "Run now" admin action; advancing the demo clock runs the promise check immediately. (US-01-001)
- Q-011 What exactly is ABC Distributors' starting data? Assumed: INV-1021 ₹4,00,000 due 11 Sep 2026 (19 days overdue), INV-1034 ₹2,00,000 due 18 Sep 2026, INV-1047 ₹1,50,000 due 25 Sep 2026; one missed promise from August; the dispute is on INV-1047. (US-01-005)
- Q-012 How is a payment split across invoices? Assumed: to the invoice its reference names; otherwise oldest due first. (US-00-019)
- Q-014 How do users sign in? Assumed: three seeded demo users (admin, collector, viewer) with a password or token; no SSO, one business. (US-01-007)
- Q-015 Who is a "high-risk customer" on the dashboard? Assumed: a customer in the HIGH priority band. (US-00-003)
- Q-016 What is the default LLM budget? Assumed: `LLM_BUDGET_USD=2.00` (about 400 calls at $0.0045). (US-01-009)
- Q-022 Which 40 replies does the database seed hold? Assumed: 38 labelled eval replies plus 2 history replies behind ABC's and Kumar's missed promises; ABC's two eval replies are live demo beats and are not pre-seeded. Evals still use all 40 from evals/replies.jsonl. (US-01-003, US-01-005)
- Q-023 Does an unclear reply ("Noted.") go to a human or get no action? Assumed: a human, as the reviewed label r-0034 and REQ-067 say; eval scenario s08 changed to match. (US-00-012)
- Q-021 Which languages do replies and drafts use? Assumed: English, including Indian English amount words (lakh, crore, L, cr); no regional scripts. (US-00-006, US-00-012)

## Register

| Q | Status | Kind | Where | Basis | Question | Readings | Decision | Why | Affects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q-001 | open | gap | REQ-067 | assumption | What confidence counts as low? | (a) fixed 0.75; (b) per class; (c) configurable, default 0.75 | (c) configurable `CLASSIFY_MIN_CONFIDENCE`, default 0.75 | brief says "low" only | US-00-012 |
| Q-002 | open | gap | REQ-026, REQ-028 | assumption | Priority weights and band cut-offs? | (a) fixed weights in code; (b) admin-tunable | (a) fixed in LLD, unit-tested; bands 60 / 35 (revised from 70 / 40 on 2026-09-30, LLD 3.2) | brief lists factors, not weights | US-00-002 |
| Q-003 | open | gap | REQ-076, REQ-077 | assumption | Match rule for payments? | (a) exact amount only; (b) amount or reference within a window; (c) fuzzy | (b), window 7 days, unique candidate | brief names amount, reference and date window | US-00-017, US-00-018 |
| Q-004 | open | gap | REQ-080 | assumption | Promise fulfilment rule? | (a) by promise date; (b) with grace days | (a), no grace | 4.24 shows fulfilment on the payment day | US-00-020 |
| Q-005 | open | open-question | REQ-075 | assumption | What does "never argue" allow? | (a) no message at all; (b) fixed acknowledgement, approval-gated | (b) | lets the operator reassure without the model arguing | US-00-016 |
| Q-006 | open | open-question | REQ-052 | assumption | Legal wording configured by the business? | (a) none; (b) a sample clause | (a) empty allow-list | brief gives none | US-00-007 |
| Q-007 | open | gap | REQ-063 | assumption | How do replies arrive? | (a) inbound SMTP; (b) simulate-reply action; (c) IMAP poll of MailHog | (b) | MailHog only catches outbound mail | US-03-001 |
| Q-008 | open | gap | REQ-091 | assumption | Trusted allow-list contents? | (a) rules listed in the entry; (b) admin-edited list | (a) in `policy/guardrails.yaml` | brief says "allow-listed gentle reminders" only | US-01-016 |
| Q-009 | open | gap | REQ-091 | assumption | Assisted batch approval semantics? | (a) approve all passed drafts in the run; (b) approve selected | (a), with single rejects first | simplest meaning of "batch" | US-01-016 |
| Q-010 | open | gap | REQ-117 | assumption | Run schedule and triggers? | (a) schedule only; (b) schedule plus manual; (c) manual only | (b); clock advance triggers promise check | demo needs manual control | US-01-001, US-01-004 |
| Q-011 | open | contradiction | REQ-110; brief 4.4 vs 4.9 | assumption | ABC invoice data? 4.9's example "INV-1021, ₹4,00,000, due 10 Sep 2026" is 20 days overdue on 30 Sep; 4.4's example says "oldest invoice 19 days overdue". | (a) due 10 Sep (20 days); (b) due 11 Sep (19 days) | (b) and the three invoices listed above | the reason text is what judges read on screen | US-01-005 |
| Q-012 | open | gap | REQ-079 | assumption | Allocation across invoices? | (a) oldest first; (b) referenced invoice first then oldest; (c) human allocates | (b) | common practice | US-00-019 |
| Q-014 | open | gap | REQ-111 | assumption | Sign-in mechanism? | (a) seeded users with password; (b) token only; (c) SSO | (a), session cookie; `ADMIN_TOKEN` for API scripts | brief names roles and `ADMIN_TOKEN` only | US-01-007 |
| Q-015 | open | gap | REQ-083 | assumption | Definition of high-risk? | (a) HIGH band; (b) separate risk score | (a) | brief ties risk to priority ("risk/priority (derived)") | US-00-003 |
| Q-016 | open | gap | REQ-095, REQ-096 | assumption | Default budget? | (a) $1; (b) $2; (c) $5 | (b) $2.00 | spike cost $0.0045 per call | US-01-009 |
| Q-021 | open | gap | REQ-048, REQ-064 | assumption | Languages? | (a) English only; (b) English plus Hinglish; (c) regional scripts | (a) with lakh/crore wording | hackathon scope | US-00-006, US-00-012 |
| Q-022 | open | contradiction | REQ-018, REQ-110 | assumption | Seed the 40 labelled replies, or keep ABC at the story start? | (a) seed all 40, ABC's promise and dispute replies appear before the reminder; (b) 38 labelled + 2 history replies | (b) | REQ-110 needs ABC with no replies at the start; the eval reads the jsonl, not the database | US-01-003, US-01-005 |
| Q-023 | open | contradiction | REQ-067, REQ-102 | assumption | Unclear reply: human review or no action? | (a) escalate below confidence 0.75; (b) no action | (a) | label r-0034 says human_review; scenario s08 said no tools | US-00-012 |
| Q-013 | open | gap | REQ-018, REQ-101 | inferred | Are the 40 seeded replies the 40 labelled eval replies? | (a) same set; (b) separate sets | (a): labels are hand-written, results come from runs | both counts are 40 in the brief | US-01-003, US-01-010 |
| Q-017 | open | gap | Non-goals | inferred | Accounting-system import in scope? | (a) no; (b) CSV import | (a) | brief specifies seed data only | US-01-003 |
| Q-018 | open | gap | Non-goals | inferred | Regional-language drafts in scope? | (a) no; (b) yes | (a) | brief is silent; office-hours cut | US-00-005 |
| Q-019 | open | gap | REQ-119 | inferred | What follows a statement request? | (a) recommend "send statement" draft; (b) escalate | (a), approval-gated | 4.1 records and follows up; no escalation named | US-00-015 |
| Q-020 | open | open-question | REQ-064 | inferred | PROMISE versus PART_PAYMENT? | (a) PROMISE = future commitment, any amount; PART_PAYMENT = partial payment made or being made now; (b) by amount | (a) | 4.24 labels "pay ₹3 lakh on October 5 and the remaining later" as PROMISE | US-00-012, US-01-005 |
