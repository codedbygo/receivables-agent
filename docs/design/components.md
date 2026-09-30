# Component contract: Collections Agent console

Every component reads roles from `docs/design/tokens.json` through CSS variables; no literal colours. Each lists its states; every interactive one has hover, focus-visible, active, disabled and loading.

| Component | Used on | Variants | States and rules |
| --- | --- | --- | --- |
| Button | all | primary (accent), quiet (border-strong outline), danger (danger text, quiet) | loading shows a spinner and keeps the label; never icon-only without an aria-label; 36 px |
| Kbd hint | Approvals | none | shows the shortcut beside the label; hidden below 768 px |
| Badge | band, status, outcome | HIGH, MEDIUM, LOW; message status; run outcome | colour plus word; never colour alone |
| Figure band | Customer, Today | 2 to 4 figures | label (13 px caps) over figure (44 px tabular) |
| Table | invoices, customers, runs | dense (36 px rows) | right-aligned money, sticky header, empty row text from the flows |
| Queue row | Approvals | current, default | aria-current on the current row; 44 px |
| Guardrail report | Approvals, Edit | all ok, has failures | one row per check: tick or error code, token, ledger value, "matches ledger" or the reason |
| Timeline | Customer | event kinds from REQ-081 | icon, actor label (AI, human, system, customer), amount in tabular figures, business date and time; newest first with a "jump to start" link |
| Dialog | Edit, Reject, Simulate reply, Resolve, Credit, Reset, Clock | form, confirm | focus trapped, Escape and Cancel close, primary action on the right |
| Toast | after actions | success, error | 150 ms slide, 5 s, dismiss button, role=status |
| Empty state | every panel | one line and one action | copy from the flows |
| Skeleton | every panel | rows, figures | no shimmer under reduced motion |
| Rail | shell | item, current | icon and label, 44 px, Admin hidden for non-admins |
| Switch | Admin sending | on, off | label states the current value in words ("Sending is on") |
