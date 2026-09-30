# Design critique: collections console, round 1

Reviewed: `docs/design/screens/console.html` (S-02, S-07, S-11, S-16) and `docs/design/variants/collections-console/1-instrument-panel.html` (S-03), at 375, 768 and 1440 px in light and dark (design-evidence: 0 problems) with contrast from `pairs.py` (0 failing). Checklist: design-critique references/review-checklist.md. Date 2026-09-30.

| # | Category (weight) | Score /10 | Evidence | Fix applied or open |
| --- | --- | --- | --- | --- |
| 1 | Hierarchy (10%) | 8 | Today opens on the attention tiles, then the figure band, then tables; Customer opens on outstanding and next action | open: Today's five tiles compete equally; make High priority wider in the build |
| 2 | Typography (15%) | 8 | Plex Condensed headings, Plex Sans body, tabular figures right-aligned; 6 sizes | none |
| 3 | Colour (10%) | 8 | one accent for primary action and current item; bands always carry words | fixed: links now use the link role instead of browser blue |
| 4 | Spacing rhythm (10%) | 8 | 8 px scale throughout; panels 24 px apart | none |
| 5 | Interaction states (10%) | 7 | every screen shows loading, empty, error, partial from the flows | open: skeletons and toasts are described, not drawn; built in Phase 8 |
| 6 | Responsive (10%) | 7 | 1440 two columns, 1100 stacks, 768 single column | fixed: 375 px tiles and figure band overflowed; now single column |
| 7 | Motion (5%) | 7 | one moment (report ticks) behind reduced motion in the variant | none |
| 8 | Content and microcopy (5%) | 9 | copy word for word from flows; verbs on buttons; errors name the next step | none |
| 9 | Accessibility (10%) | 8 | 0 failing contrast pairs in 3 contexts; focus rings; 44 px rail items | fixed: select had no visible edge (1.00:1); now border-strong |
| 10 | Consistency (10%) | 8 | same badge, table and band components across screens | fixed: MEDIUM badge wrapped; nowrap |
| 11 | AI slop detector (5%) | 9 | no gradients, no stat-card hero, no sparkle icons, agent shown as an actor not a chat | none |

Weighted score: 79 of 100. Fixes applied this round: 4. Open: 2 (tile weighting, drawn skeletons and toasts), both carried to the build.

`clarify` (ui-craft) is not installed in this session: the copy review was done against the flows' copy rules instead (verbs, next steps, no apology words), with no findings.
