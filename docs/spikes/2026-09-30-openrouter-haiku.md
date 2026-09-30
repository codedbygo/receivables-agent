# Spike: openrouter-haiku

Date: 2026-09-30   Timebox: 0.5 h, used 0.05 h (07:51 to 07:54 UTC)
Stopped because: answered
Location: none (one read-only HTTP call)
Prior work: none

## Question

What OpenRouter model id serves Claude Haiku 4.5, and does one draft or classification call cost under $0.01?

## Answered looks like

A model id present in OpenRouter's public model list, and per-token prices that put a 2,000 input + 500 output token call under $0.01.

## Operative inputs

- Brief: `max_tokens <= 500` (master prompt 4.20). Input size assumed 2,000 tokens (system prompt, customer context, invoice table); no code exists yet to measure it.
- No API key used; the models endpoint is public.

## Answer

yes: `anthropic/claude-haiku-4.5`, $1.00 per million input tokens and $5.00 per million output tokens; one 2,000 + 500 token call costs $0.0045.

## Findings

| Time (UTC) | Finding | Evidence |
| --- | --- | --- |
| 07:51 | Model id `anthropic/claude-haiku-4.5`, context 200,000 | `curl -s https://openrouter.ai/api/v1/models \| jq '.data[] \| select(.id\|test("haiku"))'` |
| 07:51 | Price per token: prompt 0.000001, completion 0.000005 (USD) | same output |
| 07:51 | Alias `~anthropic/claude-haiku-latest` exists and floats to newer versions | same output |
| 07:51 | `:batch` variant at half price is not usable for interactive drafting | same output |

Measured on: laptop, public API.

## Not run or not measured

- No completion call made (no key in this session). Latency, rate limits and whether OpenRouter returns `usage.cost` in the response are unverified; the gateway computes cost from its own pricing table either way.
- Real input token counts: measured once prompts exist (prompt-registry).

## Tried and discarded

- None.

## Recommendation

adopt `anthropic/claude-haiku-4.5` as the default `LLM_MODEL`; never the `~...-latest` alias.

Reasoning: a pinned id keeps replay fixtures and eval numbers comparable across runs; the alias would change behaviour silently. At $0.0045 per call, a daily run over 15 customers plus 40 eval replies costs about $0.25, so `LLM_BUDGET_USD=2.00` is a safe default.

## Follow-up

- Task: "Pricing table in the LLM gateway: haiku-4.5 1.00/5.00 USD per MTok" (tracker: none)
- ADR needed: yes (LLM choice, Phase 3)

## Throwaway

No code was written.
