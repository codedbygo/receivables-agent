"""US-01-001, US-00-008: the bounded Collections loop, its trajectory, and the template fallback."""

import json
import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, text

from app.agent.orchestrator import Orchestrator, redact
from app.core.config import Settings
from app.llm.gateway import Gateway
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
PROSE = (
    "Dear ABC Distributors,\n\nThese invoices are past due:\n\n{{invoice_table}}\n\nTotal outstanding: {{total}}"
    "\n\nWe had noted your plan in August. Could you confirm a payment date this week?\n\nRegards,\nAccounts team"
)


def call(name: str, args: dict[str, object]) -> dict[str, object]:
    msg = {
        "content": None,
        "tool_calls": [
            {"id": f"c-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }
    return {"choices": [{"message": msg}], "usage": {"prompt_tokens": 800, "completion_tokens": 60}}


def final(text_: str = "done") -> dict[str, object]:
    return {
        "choices": [{"message": {"content": text_}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 5},
    }


def orch(
    engine: Engine, bodies: list[dict[str, object]], mode: str = "live", tmp: Path | None = None
) -> Orchestrator:
    queue = list(bodies)
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=queue.pop(0)))
    settings = Settings(database_url=os.environ["DATABASE_URL"], llm_mode=mode, openrouter_api_key="k")  # type: ignore[arg-type]
    gw = Gateway(settings, engine, transport=transport, sleep=lambda _s: None, fixtures_dir=tmp)
    return Orchestrator(engine, gw, build_registry(engine))


@pytest.fixture
def seeded(engine: Engine) -> Engine:
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    return engine


def rows(engine: Engine, sql: str) -> list[tuple[object, ...]]:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(sql))]


# TC-0170 (AC-US-01-001-1), TC-0171 (AC-US-01-001-2)
def test_history_then_draft_waits_for_approval(seeded: Engine) -> None:
    o = orch(
        seeded,
        [
            call("get_customer_history", {"customer_id": ABC}),
            call("draft_message", {"customer_id": ABC, "kind": "reminder", "prose": PROSE, "tone": "firm"}),
            final(),
        ],
    )

    run = o.run_collections(ABC, "manual")

    assert (run.outcome, run.tool_call_count, run.tone, run.channel) == (
        "WAIT_FOR_APPROVAL",
        2,
        "firm",
        "email",
    )
    assert rows(
        seeded, f"SELECT seq, tool_name, role FROM agent_steps WHERE agent_run_id = '{run.id}' ORDER BY seq"
    ) == [(1, "get_customer_history", "collections"), (2, "draft_message", "collections")]
    assert rows(seeded, f"SELECT status FROM messages WHERE agent_run_id = '{run.id}'") == [
        ("pending_approval",)
    ]


# TC-0173 (AC-US-01-001-4)
def test_fifth_tool_call_stops_the_run(seeded: Engine) -> None:
    o = orch(seeded, [call("get_customer_history", {"customer_id": ABC})] * 5 + [final()])

    run = o.run_collections(ABC, "manual")

    assert (run.outcome, run.tool_call_count) == ("STOPPED_LIMIT", 4)
    assert "tool-call limit 4" in (run.reason or "")
    assert rows(seeded, "SELECT count(*) FROM guardrail_events WHERE code = 'TOOL_LIMIT'") == [(1,)]


def test_model_asking_for_send_is_refused_and_counted(seeded: Engine) -> None:
    o = orch(
        seeded,
        [
            call("get_customer_history", {"customer_id": ABC}),
            call("send_message", {"message_id": ABC}),
            call("draft_message", {"customer_id": ABC, "kind": "reminder", "prose": PROSE, "tone": "firm"}),
            final(),
        ],
    )

    run = o.run_collections(ABC, "manual")

    assert (run.outcome, run.tool_call_count) == ("WAIT_FOR_APPROVAL", 3)
    assert rows(
        seeded, f"SELECT error_code FROM agent_steps WHERE agent_run_id = '{run.id}' AND seq = 2"
    ) == [("TOOL_NOT_ALLOWED",)]


def test_no_model_available_falls_back_to_the_template(seeded: Engine, tmp_path: Path) -> None:
    o = orch(seeded, [], mode="replay", tmp=tmp_path)

    run = o.run_collections(ABC, "manual")

    assert run.outcome == "WAIT_FOR_APPROVAL"
    assert "template" in (run.reason or "") and "REPLAY_MISS" in (run.reason or "")
    body = str(rows(seeded, f"SELECT body FROM messages WHERE agent_run_id = '{run.id}'")[0][0])
    assert "INV-1021 | ₹4,00,000 | due 11 Sep 2026" in body and "₹7,50,000" in body


def test_arguments_are_redacted_in_the_trajectory(seeded: Engine) -> None:
    o = orch(
        seeded,
        [
            call(
                "log_promise", {"customer_id": ABC, "amount_paise": 30_000_000, "promised_date": "2026-10-05"}
            ),
            final(),
        ],
    )

    run = o.run_collections(ABC, "manual")

    args = rows(seeded, f"SELECT arguments_redacted::text FROM agent_steps WHERE agent_run_id = '{run.id}'")[
        0
    ][0]
    assert "30000000" in str(args)
    assert run.outcome == "NO_ACTION"


# TC-0174 (AC-US-01-001-5)
def test_a_second_run_while_one_is_running_is_refused(seeded: Engine) -> None:
    with seeded.begin() as c:
        c.execute(
            text(
                f"INSERT INTO agent_runs (customer_id, run_date, trigger) VALUES ('{ABC}', DATE '2026-09-30', 'manual')"
            )
        )
    o = orch(seeded, [])

    assert o.run_collections(ABC, "manual") is None


def test_all_open_invoices_disputed_escalates_instead_of_drafting(seeded: Engine, tmp_path: Path) -> None:
    andhra = uid("customer", "Andhra Industrial Supplies")
    with seeded.begin() as c:
        c.execute(text("UPDATE invoices SET status = 'disputed' WHERE number = 'INV-1410'"))
        c.execute(
            text("""INSERT INTO disputes (customer_id, invoice_id, reason)
            SELECT customer_id, id, 'Short supply' FROM invoices WHERE number = 'INV-1410'""")
        )
    o = orch(seeded, [], mode="replay", tmp=tmp_path)

    run = o.run_collections(andhra, "scheduled")

    assert run.outcome == "ESCALATED"
    assert rows(seeded, f"SELECT count(*) FROM messages WHERE customer_id = '{andhra}'") == [(0,)]


def test_model_cannot_log_a_promise_or_act_on_another_customer(seeded: Engine) -> None:
    # Security review 2026-10-01: a model-chosen promise amount would enter the ledger and the verifier's
    # allowed amounts (tenet 1); a model-chosen customer_id would act outside the run's customer.
    metro = uid("customer", "Metro Wholesale")
    o = orch(
        seeded,
        [
            call(
                "log_promise", {"customer_id": ABC, "amount_paise": 12345600, "promised_date": "2026-09-29"}
            ),
            call("get_customer_history", {"customer_id": metro}),
            final(),
        ],
    )

    run = o.run_collections(ABC, "manual")

    assert rows(
        seeded, f"SELECT error_code FROM agent_steps WHERE agent_run_id = '{run.id}' AND seq = 1"
    ) == [("TOOL_NOT_ALLOWED",)]
    assert rows(seeded, "SELECT count(*) FROM promises WHERE amount_paise = 12345600") == [(0,)]
    steps = rows(
        seeded, f"SELECT arguments_redacted FROM agent_steps WHERE agent_run_id = '{run.id}' AND seq = 2"
    )
    assert steps[0][0]["customer_id"] == ABC  # type: ignore[index]


def test_malformed_model_response_uses_the_template_and_frees_the_customer(seeded: Engine) -> None:
    # Review 2026-10-01: a response with no choices raised KeyError, left agent_runs 'running' and blocked the customer.
    o = orch(seeded, [{"id": "x", "object": "chat.completion"}, final()])

    run = o.run_collections(ABC, "manual")

    assert run is not None and run.outcome == "WAIT_FOR_APPROVAL"
    assert o.run_collections(ABC, "manual") is not None  # not blocked by a stuck 'running' row


def test_unexpected_error_in_a_run_fails_it_and_frees_the_customer(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise ZeroDivisionError

    o = orch(seeded, [final()])
    monkeypatch.setattr(o, "_model_loop", boom)

    with pytest.raises(ZeroDivisionError):
        o.run_collections(ABC, "manual")

    assert rows(seeded, f"SELECT status, outcome FROM agent_runs WHERE customer_id = '{ABC}'") == [
        ("finished", "FAILED")
    ]


# Audit finding 4: the model cannot pick the one kind that skips the disputed-invoice rule.
def test_model_cannot_draft_a_dispute_ack(seeded: Engine) -> None:
    o = orch(
        seeded,
        [
            call(
                "draft_message", {"customer_id": ABC, "kind": "dispute_ack", "prose": PROSE, "tone": "firm"}
            ),
            final(),
        ],
    )

    run = o.run_collections(ABC, "manual")

    assert rows(seeded, f"SELECT kind FROM messages WHERE agent_run_id = '{run.id}'") == [("reminder",)]


# TC-0191 (AC-US-00-008-2): emails, phones and free text never reach the trajectory.
def test_emails_phones_and_bodies_are_redacted_in_steps(seeded: Engine) -> None:
    reason = "Ravi wrote from ravi@abc-distributors.example.in, call +91 98765 43210"
    o = orch(
        seeded, [call("escalate", {"customer_id": ABC, "kind": "low_confidence", "reason": reason}), final()]
    )

    run = o.run_collections(ABC, "manual")

    stored = str(
        rows(seeded, f"SELECT arguments_redacted::text FROM agent_steps WHERE agent_run_id = '{run.id}'")
    )
    assert "[redacted:email]" in stored and "[redacted:phone]" in stored
    assert "ravi@abc" not in stored and "98765" not in stored
    assert redact({"body": "We will pay on Friday"}) == {"body": "[redacted:text]"}


# Brief 9.2: three bounds stop a runaway model (the registry's limit, the agent_steps seq constraint, the loop).
# With the first two switched off, the loop's own bound still stops it; the constraint is restored in finally.
def test_the_model_loop_is_bounded_even_without_the_other_two_limits(seeded: Engine) -> None:
    o = orch(seeded, [call("get_customer_history", {"customer_id": ABC})] * 5)
    started = o._start(ABC, "manual")
    assert started is not None
    run_id, d = started
    ctx = ToolContext(actor="ai", source="agent", run_id=run_id)  # no max_calls: the registry does not count
    with seeded.begin() as c:
        c.execute(text("ALTER TABLE agent_steps DROP CONSTRAINT chk_agent_steps_seq"))
    try:
        reason = o._model_loop(run_id, ctx, ABC, "firm", "email", d)
    finally:
        with seeded.begin() as c:
            c.execute(text("DELETE FROM agent_steps WHERE seq > 4"))
            c.execute(
                text("ALTER TABLE agent_steps ADD CONSTRAINT chk_agent_steps_seq CHECK (seq BETWEEN 1 AND 4)")
            )

    assert reason == "tool-call limit 4 reached" and ctx.calls == 5


def test_the_template_draft_is_skipped_when_the_history_cannot_be_read(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    o = orch(seeded, [])
    monkeypatch.setattr(o, "invoke", lambda *_a: {"ok": False, "error": {"code": "NOT_FOUND"}})

    o._template(uid("none", "run"), ToolContext(actor="ai", source="agent"), ABC, "firm", "email")

    assert rows(seeded, f"SELECT count(*) FROM messages WHERE customer_id = '{ABC}'") == [(0,)]
