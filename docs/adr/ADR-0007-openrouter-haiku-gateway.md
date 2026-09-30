# ADR-0007: Use OpenRouter with a pinned Claude Haiku 4.5 id behind one gateway

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: llm
- Reversibility: cheap: model id is configuration

## Context

The brief fixes OpenRouter to Claude Haiku 4.5 with a configurable id, max_tokens <= 500, budget, retries and live/replay/record modes. The spike found id anthropic/claude-haiku-4.5 at $1 and $5 per million tokens; an alias ~anthropic/claude-haiku-latest floats.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| anthropic/claude-haiku-4.5, pinned (chosen) | manual bump for new versions | n/a |
| ~anthropic/claude-haiku-latest | behaviour changes silently; replay fixtures and eval numbers drift | exploratory use without evals |

## Decision

We will call OpenRouter only through one gateway with LLM_MODEL=anthropic/claude-haiku-4.5, LLM_MAX_TOKENS capped at 500 and LLM_BUDGET_USD=2.00 by default, because pinning keeps replay keys and eval numbers stable.

## Consequences

Replay key: prompt name and version plus sha256 of normalised input.

## Commits us to

OpenRouter, Claude Haiku 4.5
