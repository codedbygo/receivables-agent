# GenAI solution: collections drafting and reply understanding

- Task: HACK-001
- Serves: REQ-029 to REQ-036, REQ-046 to REQ-052, REQ-063 to REQ-068, REQ-093 to REQ-105; ADR-0005, ADR-0007, ADR-0012
- Status: Accepted (Phase 6, 2026-09-30)

## 1. Problem

A collector writes the same reminder dozens of times a day and reads replies in messy Indian business English ("will do 3L by 5th, bal next month"). The system must draft reminders that are correct to the paise and understand replies well enough to log promises, disputes and payment claims, without ever letting the model decide a number.

## 2. Success metric

- Drafts: 100% of red-team drafts rejected and 100% of golden drafts accepted by the guardrails (REQ-103); 0 sent messages with a figure that differs from the ledger.
- Replies: class accuracy ≥ 36/40, amount exact ≥ 38/40 where an amount exists, date exact ≥ 37/40 where a date exists, on `evals/replies.jsonl` in replay mode (targets set here; the run prints the actual numbers).
- Agent: ≥ 10 of 10 trajectory scenarios pass (class, tool sequence, final outcome).
- Cost: ≤ $0.25 for a worst-case daily run of 15 customers.

## 3. Task class

Two LLM tasks, both small: (1) constrained generation of prose around placeholders, with a bounded tool-use loop; (2) classification plus span extraction on short untrusted text. Everything numeric, temporal or decisional is deterministic code (tenets 1, 2, 5).

## 4. Approach

| Option | Verdict | Why |
| --- | --- | --- |
| Templates only, no LLM | rejected for drafting prose, kept as fallback | cheapest and safest, but reads robotic and cannot reference history ("we had noted your plan in August"); the fixed dispute acknowledgement stays a template |
| Regex and rules for replies | rejected as the primary classifier, kept for injection flags and number parsing | brittle on "3L by 5th, bal next month"; used to parse and validate the model's spans |
| LLM drafts prose around placeholders + code-filled figures + deterministic verifier (chosen) | chosen | natural prose, zero model-authored figures, every output checked |
| LLM classifies replies with no tools; code parses amounts and dates from the returned spans (chosen) | chosen | the model finds the intent and the spans; code decides the values; injection has no tool to reach |
| RAG, fine-tuning, multi-agent | not needed | no document corpus; 40 labelled replies is an eval set, not training data |

## 5. Model and budget

- Model: `anthropic/claude-haiku-4.5` via OpenRouter, pinned (ADR-0007). Small tasks, short context, latency matters in a live demo.
- Tokens per call: drafting about 1,800 input and 250 output; classification about 900 input and 150 output; `max_tokens` 500.
- Cost: drafting turn about $0.0031, classification about $0.0017. Daily run of 15 customers at 3 turns each: about $0.14; worst case 5 turns: about $0.23. The 40-reply eval in live mode: about $0.07.
- Budget: `LLM_BUDGET_USD=2.00` default with reservation under a lock (LLD 7.1). CI and demos run in replay (cost 0).

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Model writes a figure or invoice that is wrong | placeholders plus the verifier on the final text (LLD 6.1); red-team set in CI |
| Prompt injection in a reply | classification has no tools; delimited input; injection regexes force escalation; code parses values |
| Unsafe tone | tone set by code; tone lexicon on output; approval gate |
| Replay fixtures go stale when the seed or a prompt changes | manifest with seed hash and prompt versions; REPLAY_MISS names the key |
| OpenRouter slow or down on stage | replay default for the demo; live shown once |
| Model returns a class outside the seven | schema validation; CLASS_INVALID escalates |

## 7. Evaluation plan

- `evals/replies.jsonl`: 40 hand-labelled replies (class, amount in paise, date against the demo clock 2026-09-30, invoice refs, expected action); graded by exact match in code.
- `evals/scenarios/*.yaml`: 12 trajectory scenarios; graded by class, tool sequence and final outcome.
- `evals/redteam.yaml`: 18 bad drafts (invented amount, wrong total, wrong customer, nonexistent invoice, another customer's invoice, impossible date, threat, legal, shaming, third party, false urgency); each must be rejected with the expected code.
- `evals/golden.yaml`: 6 correct drafts; each must pass.
- `make eval` runs all four in replay; CI fails on any red-team pass, any golden rejection, or class accuracy below the committed baseline (`evals/baseline.json`, written after the first recorded run).

## 8. Open questions

- Are 40 replies enough to trust the class accuracy? Not statistically; they are a regression gate. Owner: AI lead rotation; grow to 100 from real replies after the hackathon.
