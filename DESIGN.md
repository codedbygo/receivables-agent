# Design System: Collections Agent console

Source of truth for values: `docs/design/tokens.json` (contrast: 68 pairs, 0 below minimum). Direction chosen in round 1: `docs/design/variants/collections-console/approved.json` (Instrument panel, with the Swiss grid's figure band and the Ledger's total rule). Flows: `docs/design/flows/collections-console/flows.md`.

## Product Context

A collections operations console for Indian B2B finance teams. Users: collectors working a daily queue at a desk, admins running the system (and the demo on a projector), viewers. The one thing to remember: every number on screen has been checked against the ledger, and the screen shows the check.

## Aesthetic Direction

Instrument panel: cool graphite surfaces, dense ruled rows, tabular figures, one teal accent for the primary action and current position. Calm, not dramatic; nothing decorative. Not a chatbot: the agent appears as an actor on the timeline and in the run viewer, never as a chat bubble.

## Typography

- Display: IBM Plex Sans Condensed 600 (headings, figure band). Body: IBM Plex Sans 400/600. Data: IBM Plex Mono for codes (INV-1021, error codes, redacted arguments).
- Sizes (px): label 13, body 15, title 18, heading 22, display 28, figure 44 (figure band only).
- All money and counts use `font-variant-numeric: tabular-nums` and are right-aligned in tables.
- Fonts are self-hosted through `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-sans-condensed` and `@fontsource/ibm-plex-mono` in the web build (no third-party font host at runtime).

## Color

Roles only in code (`--color-<role>`), never primitives or hex. Accent (teal 700 light, 400 dark) has one job: the primary action and the current position. Bands: HIGH uses danger, MEDIUM warning, LOW text-muted, each always with its word. Verified ticks use success with the words "matches ledger". Errors use danger and always start with the word "Error:" or the code.

## Spacing

8 px base with one 4 px half step: 0, 4, 8, 16, 24, 32, 48, 64. Table rows 36 px; list rows 44 px when they are the whole target.

## Layout

App shell: 64 px icon-and-label rail, content to the right. Approvals: queue column 320 px, draft centre, guardrail report right (280 px). Customer page: figure band (outstanding, oldest overdue, priority, next action) over a two-column body (timeline main, invoices and promises aside). Max content width 1440 px. Below 1100 px the queue collapses into a list page and the report moves under the draft; below 768 px single column.

## Motion

One moment per page: the guardrail report ticks reveal in sequence (stagger 60 ms, base 240 ms, transform and opacity). Toasts slide in 150 ms. Under `prefers-reduced-motion` everything renders in its end state.

## Focus and accessibility

2 px focus ring (role focus) with 2 px offset on every control, never removed. Targets: 36 px pointer controls, 44 px list rows and rail items. Keyboard: J/K move in the queue, A approve, E edit, R reject, with visible hints; focus moves to the next draft after an action. Status is never colour only. WCAG 2.2 AA in both themes.

## Themes

Light and dark, designed separately (tokens `color.roles.light` and `.dark`). The theme follows the system, with a toggle in the rail stored per user in localStorage.

## Decisions Log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-09-30 | Instrument panel direction (score 84 of 100) | best fit for dense daily queue work; docs/design/variants/collections-console/approved.json |
| 2026-09-30 | Borrow the figure band and the double-ruled total | projector legibility for the demo; the total reads as a ledger line |
| 2026-09-30 | IBM Plex self-hosted | no runtime font host on a slow network |
