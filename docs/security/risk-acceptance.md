# Risk acceptance and open findings

Source: read-only audit by the `bearing:security-auditor` agent on 2026-10-02, a stand-in for `/cso --diff`
(the helper refused to start in the sandbox: "Private state ancestor has an unexpected owner"). The findings
are unverified claims until `/cso --diff` and `claude-security` run on the release commit.

| # | Finding | State |
| --- | --- | --- |
| 1 | Role header is the only credential | Fixed: ADR-0013, tests in tests/unit/test_auth_tokens.py |
| 2 | Pay-link token written to the request log | Fixed: log keeps the route template, test in tests/api/test_health.py |
| 3 | No frame-ancestors | Fixed in frontend/nginx.conf; not run (no nginx here) |
| 4 | Model could pick kind dispute_ack | Fixed in orchestrator; tests/service/test_orchestrator.py::test_model_cannot_draft_a_dispute_ack passes against Postgres |
| 5 | Payment-details guardrail gaps | Fixed: UPI ids, spaced digits, NFKC; tests in tests/unit/test_verify.py |
| 6 | Batch approve has no version check | Fixed: the batch carries `{id, version}` per draft; a changed draft refuses the whole batch (STALE_DRAFT). Contract in api/openapi.yaml, web Approvals page, test_batch_approval_refuses_a_draft_that_changed_after_it_was_shown |
| 7 | MCP tools do not bind reply, dispute or payment ids to the customer | Fixed: `_owned` in services/collections.py for log_promise, log_dispute, escalate; three tests in tests/tool/test_registry.py |
| 8 | No rate limiting | Partly fixed: nginx limit_req on /api/ (not run). No per-role limits in the API |
| 9 | Webhook buffers an unbounded chunked body | Fixed: read_capped, tests/unit/test_webhook_body.py |
| 10 | No dependency audit target; images and actions float | Scanned once by hand on 2026-10-02: pip-audit on the uv.lock export (168 pins) and `pnpm audit --prod` both report no known vulnerabilities. `make audit` added and run by the CI security job (passes). Still open: images and actions float |
| 11 | Run reads by id skip the role check; unknown run id gives 500 | Refuted: roles match api/openapi.yaml x-roles (viewers read a customer's trajectory by design) and an unknown id already returns 404; regression test test_an_unknown_run_id_is_404_not_500 |
| 12 | Default ALLOWED_HOSTS includes testserver and api | Open (low; needs local DNS control) |

Accepted for the hosted demo: pay link and "simulate credit" settle invoices with no real money moving, by design.
They stay behind FEATURE_PAYMENT_LINK and the admin role. No customer erasure path exists; demo data only.
