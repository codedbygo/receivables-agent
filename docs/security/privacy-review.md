# Privacy review: collections agent (HACK-001)

Lightweight review, 2026-10-01. Scope: customer contact data, message and reply bodies, agent trajectories,
LLM traffic and logs. All data in this build is seeded demo data on `@example.in` style domains.

## Data map

| Data | Where it lives | Who reads it | Leaves the system? | Control |
| --- | --- | --- | --- | --- |
| Customer name, email, phone | `customers` | every signed-in role | email to the mail catcher; name in LLM prompts | demo domains only; the role header gates reads |
| Draft and sent message bodies | `messages` | every role (approval queue) | SMTP to Mailpit only | sends need approval and the kill switch off |
| Customer reply text | `replies` | every role (customer page) | to the LLM for classification, wrapped as untrusted data | `get_customer_history` returns no reply bodies (`test_history_has_no_reply_bodies`) |
| Agent tool arguments | `agent_steps.arguments_redacted` | every role (trajectory viewer) | no | `orchestrator.redact`: `body` and `reply_text` replaced, emails and phones masked |
| LLM call records | `llm_calls` | admin | no | stores prompt name, version, model, replay key and cost; no prompt or response text |
| Replay fixtures | `evals/fixtures/**.json` (none recorded yet, D-007; committed once recorded) | anyone with the repo | yes, in git | record on seeded customers only |
| Application logs | stdout (JSON) | operator | no | ids and codes only; no bodies, emails or phones (`test_logging.py`) |

## Findings

1. Replay fixtures, once recorded (D-007), are committed with model output that names customers. Acceptable for
   seeded data; recording against real customer data would publish it. Action before any real data: keep fixtures
   out of git or record them on synthetic data only.
2. Every role, including viewer, can read reply bodies and customer contact details. Fine for the demo roles;
   a real deployment needs per-resource authorisation (the security rules) and a reason to show reply text to
   viewers at all.
3. Reply text is sent to OpenRouter in live mode. A real deployment needs a data processing agreement and a
   statement to customers that replies are processed by a third-party model.
4. No retention rule exists for replies, messages or trajectories. Needed before real data: a retention period
   and a purge job.

None of these block the demo. Item 1 is DEBT D-010; items 2 to 4 are D-011.
