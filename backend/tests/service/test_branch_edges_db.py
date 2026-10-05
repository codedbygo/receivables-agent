"""Branches with no test until the coverage pass of 2026-10-02, each named after the behaviour it proves:
refusals on bad input, not-found ids, state guards, races, and the send worker's failure paths."""

import os
import threading
import time
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import DeadlockDetected
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.api.routers.records as records
from app.agent import replies
from app.agent.orchestrator import Orchestrator
from app.api.main import create_app
from app.channels.email import ChannelError, Outbound
from app.core.config import Settings
from app.core.errors import AppError
from app.llm.gateway import Gateway
from app.services import approval, demo, overview, payments
from app.services.auth import demo_user
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry
from app.worker.jobs import reap

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
ADMIN, COLLECTOR = {"X-Demo-Role": "admin"}, {"X-Demo-Role": "collector"}
SECRET = "test-bank-secret"
PROSE = (
    "Dear ABC Distributors,\n\nThese invoices are past due:\n\n{{invoice_table}}\n\nTotal outstanding: {{total}}"
    "\n\nCould you confirm a payment date this week?\n\nRegards,\nAccounts team"
)


@pytest.fixture
def settings(engine: Engine) -> Settings:
    s = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, s)
    return s


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def code(out: dict[str, object]) -> object:
    error = out.get("error")
    return error.get("code") if isinstance(error, dict) else None


def one(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def tool(engine: Engine, name: str, args: dict[str, object]) -> dict[str, object]:
    return build_registry(engine).invoke(name, args, ToolContext(actor="ai", source="mcp"))


def draft(engine: Engine, **extra: object) -> dict[str, object]:
    return tool(
        engine,
        "draft_message",
        {"customer_id": ABC, "kind": "reminder", "prose": PROSE, "tone": "firm", **extra},
    )


def approved_message(engine: Engine) -> str:
    out = draft(engine)
    data = out["data"]
    assert isinstance(data, dict)
    mid = str(data["message_id"])
    with Session(bind=engine) as s, s.begin():
        approval.approve(s, mid, None, None)
    return mid


def credit(engine: Engine, event: str, amount: int, reference: str) -> payments.Payment:
    with Session(bind=engine) as s, s.begin():
        return payments.receive_credit(
            s, payments.BankCredit(event_id=event, amount_paise=amount, reference=reference)
        )


# --- drafting refusals -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("invoices", "expected"),
    [(["INV-9999"], "INVOICE_NOT_FOUND"), (["INV-1301"], "INVOICE_WRONG_CUSTOMER")],
)
def test_a_draft_citing_a_bad_invoice_is_refused(
    settings: Settings, engine: Engine, invoices: list[str], expected: str
) -> None:
    assert code(draft(engine, invoice_numbers=invoices)) == expected


def test_a_reminder_citing_a_disputed_invoice_is_refused(settings: Settings, engine: Engine) -> None:
    tool(
        engine, "log_dispute", {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "short delivery"}
    )

    assert code(draft(engine, invoice_numbers=["INV-1047"])) == "INVOICE_DISPUTED"


def test_a_reminder_for_a_customer_with_nothing_overdue_is_refused(
    settings: Settings, engine: Engine
) -> None:
    clean = one(
        engine,
        """SELECT c.id::text FROM customers c WHERE NOT EXISTS (SELECT 1 FROM invoices i JOIN invoice_balances b
        ON b.invoice_id = i.id WHERE i.customer_id = c.id AND b.remaining_paise > 0 AND i.due_date < DATE '2026-09-30')
        ORDER BY c.name LIMIT 1""",
    )

    out = tool(
        engine, "draft_message", {"customer_id": clean, "kind": "reminder", "prose": PROSE, "tone": "gentle"}
    )

    assert code(out) == "VALIDATION_ERROR"


# --- registry tools ---------------------------------------------------------------------------------------
def test_get_invoice_names_an_unknown_invoice(settings: Settings, engine: Engine) -> None:
    assert code(tool(engine, "get_invoice", {"invoice_number": "INV-9999"})) == "INVOICE_NOT_FOUND"


def test_record_payment_matches_an_unassigned_credit_and_refuses_another_customers(
    settings: Settings, engine: Engine
) -> None:
    credit(engine, "evt-free", 5_000_000, "NEFT UNKNOWN PAYER")
    credit(engine, "evt-other", 5_000_000, "INV-1301")

    free = tool(engine, "record_payment", {"customer_id": ABC, "bank_event_id": "evt-free"})
    again = tool(engine, "record_payment", {"customer_id": ABC, "bank_event_id": "evt-free"})
    other = tool(engine, "record_payment", {"customer_id": ABC, "bank_event_id": "evt-other"})

    assert free["ok"] and again["ok"]
    assert code(other) == "NO_LEDGER_EVIDENCE"


def test_classify_reply_tool_classifies_a_stored_reply_and_names_an_unknown_one(
    settings: Settings, engine: Engine
) -> None:
    data = draft(engine)["data"]
    assert isinstance(data, dict)
    with Session(bind=engine) as s, s.begin():
        rid, _ = replies.ingest(s, str(data["message_id"]), "We can pay 3 lakh on October 5.")

    known = tool(engine, "classify_reply", {"reply_id": rid})
    unknown = tool(engine, "classify_reply", {"reply_id": uid("none", "reply")})

    assert isinstance(known["data"], dict) and known["data"]["classification"] == "PROMISE"
    assert code(unknown) == "NOT_FOUND"


def test_logging_the_same_reply_twice_returns_the_first_promise(settings: Settings, engine: Engine) -> None:
    data = draft(engine)["data"]
    assert isinstance(data, dict)
    with Session(bind=engine) as s, s.begin():
        rid, _ = replies.ingest(s, str(data["message_id"]), "We can pay 3 lakh on October 5.")
    args = {"customer_id": ABC, "amount_paise": 30_000_000, "promised_date": "2026-10-05", "reply_id": rid}

    first = build_registry(engine).invoke("log_promise", args, ToolContext(actor="human", source="api"))
    second = build_registry(engine).invoke("log_promise", args, ToolContext(actor="human", source="api"))

    assert first["data"] == second["data"]


# --- replies ----------------------------------------------------------------------------------------------
def test_a_reply_to_an_unknown_message_is_refused(settings: Settings, engine: Engine) -> None:
    with Session(bind=engine) as s, s.begin(), pytest.raises(AppError) as e:
        replies.ingest(s, uid("none", "message"), "hello")

    assert e.value.code == "NOT_FOUND"


def test_a_reply_while_a_run_is_in_progress_is_refused_and_so_is_a_second_run(
    settings: Settings, engine: Engine, api: TestClient
) -> None:
    o = Orchestrator(engine, Gateway(settings, engine), build_registry(engine))
    data = draft(engine)["data"]
    assert isinstance(data, dict)
    with Session(bind=engine) as s, s.begin():
        rid, _ = replies.ingest(s, str(data["message_id"]), "We can pay 3 lakh on October 5.")
    assert o._start(ABC, "manual") is not None  # a run holds the customer

    with pytest.raises(AppError) as e:
        replies.understand(o, rid)
    run = api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN)

    assert e.value.code == "VALIDATION_ERROR"
    assert run.json()["error"]["code"] == "VALIDATION_ERROR"


# --- API guards -------------------------------------------------------------------------------------------
def test_an_if_match_that_is_not_a_version_is_refused(
    settings: Settings, engine: Engine, api: TestClient
) -> None:
    data = draft(engine)["data"]
    assert isinstance(data, dict)

    r = api.patch(
        f"/api/v1/messages/{data['message_id']}",
        json={"subject": "s", "body": "b"},
        headers={**COLLECTOR, "If-Match": "latest"},
    )

    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_the_evaluation_page_says_when_no_evaluation_has_run(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(records, "latest", lambda: None)

    assert api.get("/api/v1/evals/latest", headers=COLLECTOR).status_code == 404


def test_a_payment_link_for_an_unknown_invoice_is_refused(api: TestClient) -> None:
    api.patch("/api/v1/admin/settings", json={"feature_payment_link": True}, headers=ADMIN)

    r = api.post("/api/v1/invoices/INV-9999/pay-link", headers=COLLECTOR)

    assert r.json()["error"]["code"] == "INVOICE_NOT_FOUND"


def test_switching_trusted_mode_off_returns_autonomy_to_manual(api: TestClient) -> None:
    api.patch(
        "/api/v1/admin/settings",
        json={"feature_trusted_mode": True, "autonomy_mode": "trusted"},
        headers=ADMIN,
    )

    r = api.patch("/api/v1/admin/settings", json={"feature_trusted_mode": False}, headers=ADMIN)

    assert r.json()["autonomy_mode"] == "manual"


# --- disputes ---------------------------------------------------------------------------------------------
def test_resolving_a_dispute_needs_a_note_a_known_id_and_happens_once(
    settings: Settings, engine: Engine, api: TestClient
) -> None:
    did = one(engine, "SELECT id::text FROM disputes WHERE status <> 'resolved' LIMIT 1")
    url = f"/api/v1/disputes/{did}/resolve"

    blank = api.post(url, json={"note": "  "}, headers=COLLECTOR)
    first = api.post(url, json={"note": "Credit note issued"}, headers=COLLECTOR)
    second = api.post(url, json={"note": "again"}, headers=COLLECTOR)
    unknown = api.post(f"/api/v1/disputes/{uid('none', 'd')}/resolve", json={"note": "x"}, headers=COLLECTOR)

    assert blank.json()["error"]["code"] == "REASON_REQUIRED"
    assert first.json()["status"] == "resolved" and second.json()["status"] == "resolved"
    assert unknown.status_code == 404


# --- next action ------------------------------------------------------------------------------------------
def test_the_next_action_follows_drafts_promises_and_overdue_invoices(
    settings: Settings, engine: Engine
) -> None:
    kumar = uid("customer", "Kumar Electricals")
    with engine.begin() as c:
        c.execute(text(f"DELETE FROM disputes WHERE customer_id = '{kumar}'"))
        c.execute(text(f"UPDATE promises SET status = 'fulfilled' WHERE customer_id = '{kumar}'"))
    d = date(2026, 9, 30)

    with Session(bind=engine) as s:
        overdue = overview.next_action(s, kumar, d)
    with engine.begin() as c:
        c.execute(
            text(f"""INSERT INTO promises (customer_id, amount_paise, promised_date, status)
            VALUES ('{kumar}', 100000, DATE '2026-10-09', 'pending')""")
        )
    with Session(bind=engine) as s:
        pending = overview.next_action(s, kumar, d)
    tool(
        engine,
        "draft_message",
        {
            "customer_id": kumar,
            "kind": "reminder",
            "prose": PROSE.replace("ABC Distributors", "Kumar Electricals"),
            "tone": "firm",
        },
    )
    with Session(bind=engine) as s:
        drafted = overview.next_action(s, kumar, d)

    assert (overdue, pending, drafted) == (
        "Send reminder",
        "Wait for the promise due 09 Oct 2026",
        "Review the draft in Approvals",
    )


# --- payments ---------------------------------------------------------------------------------------------
def test_a_credit_of_zero_and_a_clock_advance_out_of_range_are_refused(
    settings: Settings, engine: Engine
) -> None:
    with Session(bind=engine) as s, pytest.raises(AppError) as zero:
        payments.receive_credit(s, payments.BankCredit(event_id="evt-zero", amount_paise=0, reference="x"))
    with Session(bind=engine) as s, pytest.raises(AppError) as days:
        payments.advance_clock(s, 0)

    assert zero.value.code == days.value.code == "VALIDATION_ERROR"


def test_a_credit_naming_two_customers_invoices_needs_a_human(settings: Settings, engine: Engine) -> None:
    p = credit(engine, "evt-two", 1_000_000, "INV-1021 INV-1301")

    assert p.match_status == "needs_verification"
    assert one(engine, "SELECT count(*) FROM escalations WHERE kind = 'payment_needs_verification'") == 1


def test_two_deliveries_of_one_bank_event_racing_record_one_payment(
    settings: Settings, engine: Engine
) -> None:
    other = engine.connect()
    tx = other.begin()
    other.execute(
        text("""INSERT INTO payments (amount_paise, received_on, reference, source, bank_event_id, match_status)
        VALUES (100, DATE '2026-09-30', 'race', 'bank_feed', 'evt-race', 'needs_verification')""")
    )
    got: list[payments.Payment] = []
    t = threading.Thread(target=lambda: got.append(credit(engine, "evt-race", 100, "race")))
    t.start()
    for _ in range(100):  # until the second delivery waits on the first one's row
        if one(engine, "SELECT count(*) FROM pg_locks WHERE NOT granted"):
            break
        time.sleep(0.05)  # polling Postgres lock state, not a test assertion delay

    tx.commit()
    other.close()
    t.join(timeout=30)

    assert len(got) == 1 and got[0].reference == "race"
    assert one(engine, "SELECT count(*) FROM payments WHERE bank_event_id = 'evt-race'") == 1


# --- send path --------------------------------------------------------------------------------------------
def test_approving_or_editing_a_rejected_draft_is_refused(settings: Settings, engine: Engine) -> None:
    data = draft(engine)["data"]
    assert isinstance(data, dict)
    mid = str(data["message_id"])
    with Session(bind=engine) as s, s.begin():
        approval.reject(s, mid, "wrong tone", None)

    with Session(bind=engine) as s, pytest.raises(AppError) as approved:
        approval.approve(s, mid, None, None)
    with Session(bind=engine) as s, pytest.raises(AppError) as edited:
        approval.edit(s, mid, "s", "b", None, None)

    assert approved.value.code == edited.value.code == "NOT_APPROVED"


def test_the_send_gate_refuses_an_unknown_and_a_whatsapp_message(settings: Settings, engine: Engine) -> None:
    whatsapp = approved_message(engine)
    with engine.begin() as c:
        c.execute(text(f"UPDATE messages SET channel = 'whatsapp' WHERE id = '{whatsapp}'"))

    codes = [code(tool(engine, "send_message", {"message_id": m})) for m in (uid("none", "m"), whatsapp)]

    assert codes == ["NOT_FOUND", "FEATURE_DISABLED"]


def test_the_send_gate_refuses_unverified_text_even_without_the_database_constraint(
    settings: Settings, engine: Engine
) -> None:
    # Brief 9.2: disable one layer in isolation; the next still blocks. The gate logs its refusal in its own
    # transaction, so the constraint is dropped in a committed step and put back in `finally`.
    mid = approved_message(engine)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE messages DROP CONSTRAINT chk_messages_approved_verified"))
        c.execute(text(f"UPDATE messages SET version = version + 1 WHERE id = '{mid}'"))
    try:
        with Session(bind=engine) as s, pytest.raises(AppError) as e:
            approval.send_gate(s, mid)
    finally:
        with engine.begin() as c:
            c.execute(text(f"UPDATE messages SET version = verified_version WHERE id = '{mid}'"))
            c.execute(
                text("""ALTER TABLE messages ADD CONSTRAINT chk_messages_approved_verified
                CHECK (status NOT IN ('approved','sent') OR verified_version = version)""")
            )

    assert e.value.code == "NOT_VERIFIED"


class Broken:
    simulated = False

    def send(self, _out: Outbound) -> None:
        raise ChannelError("SMTP_DOWN", retryable=True)


def test_the_send_worker_skips_a_sent_message_and_never_retries_an_unconfirmed_one(
    settings: Settings, engine: Engine
) -> None:
    sent, in_flight = approved_message(engine), approved_message(engine)
    with engine.begin() as c:
        c.execute(text(f"UPDATE messages SET status = 'sent', sent_at = now() WHERE id = '{sent}'"))
        c.execute(text(f"UPDATE messages SET last_error = 'IN_FLIGHT' WHERE id = '{in_flight}'"))

    approval.deliver(engine, sent, {"email": Broken()})
    approval.deliver(engine, in_flight, {"email": Broken()})

    assert one(engine, f"SELECT status FROM messages WHERE id = '{sent}'") == "sent"
    assert (
        one(engine, f"SELECT status || '/' || last_error FROM messages WHERE id = '{in_flight}'")
        == "failed/UNCONFIRMED"
    )


def test_the_last_failed_send_attempt_fails_the_message_on_the_timeline(
    settings: Settings, engine: Engine
) -> None:
    mid = approved_message(engine)
    with engine.begin() as c:
        c.execute(
            text(f"UPDATE messages SET send_attempts = {approval.MAX_SEND_ATTEMPTS - 1} WHERE id = '{mid}'")
        )

    with pytest.raises(ChannelError):
        approval.deliver(engine, mid, {"email": Broken()})

    assert one(engine, f"SELECT status FROM messages WHERE id = '{mid}'") == "failed"
    assert (
        one(engine, f"SELECT count(*) FROM timeline_events WHERE kind = 'send_failed' AND ref_id = '{mid}'")
        == 1
    )


def test_a_stale_job_that_is_not_a_send_is_queued_again(settings: Settings, engine: Engine) -> None:
    with engine.begin() as c:
        c.execute(
            text("""INSERT INTO jobs (kind, dedupe_key, payload, status, locked_at)
            VALUES ('promise_check', 'stale', '{}'::jsonb, 'running', now() - interval '10 minutes')""")
        )

    reap(engine)

    assert one(engine, "SELECT status FROM jobs WHERE dedupe_key = 'stale'") == "queued"


# --- seed and roles ---------------------------------------------------------------------------------------
def test_seed_refuses_a_wrong_date_and_a_seeded_database(settings: Settings, engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="DEMO_TODAY"):
        demo.seed(engine, Settings(database_url=os.environ["DATABASE_URL"], demo_today="2027-01-01"))
    with pytest.raises(RuntimeError, match="already seeded"):
        demo.seed(engine, settings)


def test_reset_gives_up_after_three_deadlocks_and_never_retries_other_errors(
    settings: Settings, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def deadlock(*_a: object) -> None:
        calls.append(1)
        raise OperationalError("LOCK", {}, DeadlockDetected())

    def other(*_a: object) -> None:
        raise OperationalError("LOCK", {}, Exception("disk full"))

    monkeypatch.setattr(demo, "_reset_once", deadlock)
    with pytest.raises(OperationalError):
        reset_demo(engine, settings)
    monkeypatch.setattr(demo, "_reset_once", other)
    with pytest.raises(OperationalError, match="disk full"):
        reset_demo(engine, settings)

    assert len(calls) == 3


def test_a_role_with_no_seeded_user_signs_nobody_in(settings: Settings, engine: Engine) -> None:
    with engine.connect() as c:
        tx = c.begin()
        c.execute(text("UPDATE users SET role = 'viewer' WHERE role = 'admin'"))
        with Session(bind=c) as s:
            user = demo_user(s, "admin")
        tx.rollback()

    assert user is None
