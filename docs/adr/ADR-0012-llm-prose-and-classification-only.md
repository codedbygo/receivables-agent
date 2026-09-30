# ADR-0012: Use the LLM only for prose around placeholders and for reply classification

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; Phase 3 approval covers the GenAI approach in docs/genai/solution.md)
- Area: genai
- Reversibility: cheap: prompts and the drafting service change; the verifier stays

## Context

The brief makes the ledger the source of truth and forbids the model from computing, inventing, rounding or totalling money (non-negotiable 2), and asks for bounded, logged agent behaviour. Replies arrive in messy Indian business English and are untrusted input.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| LLM prose around placeholders, LLM classification with no tools, code for every value (chosen) | two prompts to maintain and evaluate | n/a |
| Templates and rules only | robotic drafts, brittle reply parsing | a product with fixed wording rules from legal |
| LLM writes full drafts with numbers, verifier catches errors | more rejections, figures authored by the model | never, under non-negotiable 2 |

## Decision

We will use the model for two jobs only: prose around `{{invoice_table}}` and `{{total}}` inside a bounded tool loop, and classification with span extraction on replies with no tools available; all values are parsed and verified in code.

## Consequences

Two prompts (`draft_reminder`, `classify_reply`) and one optional (`call_prep`) live in `prompts/`, each with eval cases. Revisit if red-team or golden results regress, or if regional-language replies are added.

## Commits us to

OpenRouter, Claude Haiku 4.5 (ADR-0007)
