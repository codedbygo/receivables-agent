"""Acceptance criteria that sit at the edges of each flow: status constraints, verification, reply and payment
corner cases, the schedule, and the role matrix (traced as TC ids in docs/testing/test-cases.md)."""

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import replies
from app.agent.orchestrator import Orchestrator
from app.api.main import create_app
from app.channels.email import Outbound
from app.core.config import Settings
from app.core.paths import find_up
from app.llm.gateway import Gateway
from app.services import approval, payments
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry
from app.worker.runner import IST, schedule

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
METRO = uid("customer", "Metro Wholesale")
ADMIN, COLLECTOR, VIEWER = ({"X-Demo-Role": r} for r in ("admin", "collector", "viewer"))
PROSE = (
    "Dear {name},\n\nThese invoices are past due:\n\n{{{{invoice_table}}}}\n\nTotal outstanding: {{{{total}}}}"
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


@pytest.fixture
def orch(engine: Engine, settings: Settings, tmp_path: Path) -> Orchestrator:
    gw = Gateway(settings, engine, fixtures_dir=tmp_path)  # no fixtures: the rules classifier answers
    return Orchestrator(engine, gw, build_registry(engine, gw))


def one(engine: Engine, sql: str, **params: object) -> object:
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def draft(engine: Engine, customer: str = ABC, name: str = "ABC Distributors") -> str:
    out = build_registry(engine).invoke(
        "draft_message",
        {"customer_id": customer, "kind": "reminder", "prose": PROSE.format(name=name), "tone": "firm"},
        ToolContext(actor="ai", source="agent"),
    )
    return str(out["data"]["message_id"])


def reply(orch: Orchestrator, message_id: str, body: str) -> replies.ReplyResult:
    with Session(bind=orch.engine) as s, s.begin():
        rid, _ = replies.ingest(s, message_id, body)
    return replies.understand(orch, rid)


# --- statuses the database refuses ------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("table", "value"), [("invoices", "closed"), ("messages", "archived"), ("promises", "cancelled")]
)
def test_the_database_refuses_an_unknown_status(
    settings: Settings, engine: Engine, table: str, value: str
) -> None:
    # TC-0005 (AC-US-00-001-5), TC-0052 (AC-US-00-011-4), TC-0073 (AC-US-00-014-3)
    draft(engine)
    with engine.connect() as c, c.begin():
        c.execute(
            text(
                "INSERT INTO promises (customer_id, amount_paise, promised_date) "
                "VALUES (CAST(:c AS uuid), 100, '2026-10-05')"
            ),
            {"c": ABC},
        )

    with pytest.raises(IntegrityError, match="chk_"), engine.begin() as c:
        c.execute(text(f"UPDATE {table} SET status = :v"), {"v": value})  # noqa: S608  table from the parameter list


def test_partial_payment_leaves_the_rest_remaining(api: TestClient) -> None:
    # TC-0004 (AC-US-00-001-4)
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        headers=ADMIN,
        json={"customer_id": ABC, "amount_paise": 30_000_000, "reference": "NEFT INV-1021"},
    )

    inv = {
        i["number"]: i for i in api.get(f"/api/v1/customers/{ABC}/invoices", headers=VIEWER).json()["data"]
    }

    assert (
        inv["INV-1021"]["amount_paise"],
        inv["INV-1021"]["paid_paise"],
        inv["INV-1021"]["remaining_paise"],
    ) == (40_000_000, 30_000_000, 10_000_000)
    assert inv["INV-1021"]["status"] == "partially_paid"


# --- approval and verification ----------------------------------------------------------------------------
def test_approve_is_refused_when_the_text_changed_after_verification(api: TestClient, engine: Engine) -> None:
    # TC-0048 (AC-US-00-010-3)
    mid = draft(engine)
    with engine.begin() as c:
        c.execute(
            text("UPDATE messages SET body = body || ' ', version = version + 1 WHERE id = CAST(:m AS uuid)"),
            {"m": mid},
        )

    r = api.post(f"/api/v1/messages/{mid}/approve", headers={**COLLECTOR, "If-Match": "2"})

    assert r.json()["error"]["code"] == "NOT_VERIFIED"
    assert one(engine, "SELECT status FROM messages WHERE id = CAST(:m AS uuid)", m=mid) == "pending_approval"


def test_approval_records_the_collector_on_the_timeline(api: TestClient, engine: Engine) -> None:
    # TC-0041 (AC-US-00-009-2)
    mid = draft(engine)

    api.post(f"/api/v1/messages/{mid}/approve", headers={**COLLECTOR, "If-Match": "1"})

    events = api.get(f"/api/v1/customers/{ABC}/timeline", headers=VIEWER).json()["data"]
    approved = next(e for e in events if e["kind"] == "approved")
    assert (approved["actor"], approved["actor_name"]) == ("human", "Priya (Collector)")


def test_every_send_path_refuses_an_unapproved_message(api: TestClient, engine: Engine) -> None:
    # TC-0043 (AC-US-00-009-4), TC-0145 (AC-US-03-002-5)
    mid = draft(engine)
    ctx = ToolContext(actor="ai", source="mcp")

    mcp = build_registry(engine).invoke("send_message", {"message_id": mid}, ctx)
    with pytest.raises(Exception, match="NOT_APPROVED|approved"):
        approval.deliver(engine, mid, {})
    api_path = api.post(f"/api/v1/messages/{mid}/resend", headers=COLLECTOR)

    assert mcp["error"]["code"] == "NOT_APPROVED"
    assert api_path.json()["error"]["code"] == "NOT_APPROVED"
    assert one(engine, "SELECT count(*) FROM guardrail_events WHERE code = 'NOT_APPROVED'") >= 2  # type: ignore[operator]


def test_mcp_send_is_refused_while_the_kill_switch_is_on(api: TestClient, engine: Engine) -> None:
    # TC-0054 (AC-US-01-002-1), TC-0145 (AC-US-03-002-5)
    mid = draft(engine)
    api.post(f"/api/v1/messages/{mid}/approve", headers={**COLLECTOR, "If-Match": "1"})
    api.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=ADMIN)

    out = build_registry(engine).invoke(
        "send_message", {"message_id": mid}, ToolContext(actor="ai", source="mcp")
    )

    assert out["error"]["code"] == "SENDING_DISABLED"


def test_drafting_continues_while_sending_is_paused(api: TestClient) -> None:
    # TC-0055 (AC-US-01-002-2)
    api.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=ADMIN)

    run = api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN).json()

    msgs = api.get("/api/v1/messages", params={"filter[customer_id]": ABC}, headers=VIEWER).json()["data"]
    assert run["run_ids"] and [m["status"] for m in msgs] == ["pending_approval"]


def test_a_message_only_ever_goes_to_the_customers_stored_address(orch: Orchestrator, engine: Engine) -> None:
    # TC-0071 (AC-US-00-013-2)
    mid = draft(engine)
    reply(orch, mid, "Please send the statement to accounts@other.example.in")
    sent: list[Outbound] = []

    class Capture:
        name = "email"

        def send(self, m: Outbound) -> str:
            sent.append(m)
            return "ok"

    for m in approval_ids(engine):
        with Session(bind=engine) as s, s.begin():
            approval.approve(s, m, None, None)
        approval.deliver(engine, m, {"email": Capture()})

    stored = one(engine, "SELECT email FROM customers WHERE id = CAST(:c AS uuid)", c=ABC)
    assert sent and {m.to for m in sent} == {stored}


def approval_ids(engine: Engine) -> list[str]:
    with engine.connect() as c:
        return [
            str(x)
            for x in c.execute(
                text(
                    "SELECT id FROM messages WHERE customer_id = CAST(:c AS uuid) AND status = 'pending_approval'"
                ),
                {"c": ABC},
            ).scalars()
        ]


# --- replies ----------------------------------------------------------------------------------------------
def test_a_reply_to_another_customers_message_is_refused(api: TestClient, engine: Engine) -> None:
    # TC-0059 (AC-US-03-001-2)
    mid = draft(engine, METRO, "Metro Wholesale")
    with Session(bind=engine) as s, s.begin(), pytest.raises(Exception, match="another customer"):
        replies.ingest(s, mid, "We will pay", customer_id=ABC)


def test_a_statement_request_drafts_a_statement_of_every_open_invoice(
    api: TestClient, engine: Engine
) -> None:
    # TC-0074 (AC-US-00-015-1), TC-0075 (AC-US-00-015-2)
    mid = draft(engine)
    r = api.post(
        "/api/v1/replies",
        headers=COLLECTOR,
        json={"message_id": mid, "body": "Please send us a statement of account."},
    ).json()

    [st] = api.get("/api/v1/messages", params={"filter[customer_id]": ABC}, headers=VIEWER).json()["data"][:1]
    assert r["classification"] == "STATEMENT_REQUEST" and r["recommended_action"] == "send_statement"
    assert st["kind"] == "statement" and st["status"] == "pending_approval" and st["verified"]
    assert st["invoice_numbers"] == ["INV-1021", "INV-1034", "INV-1047"] and "₹7,50,000" in st["body"]


def test_a_low_confidence_reply_goes_to_a_human(orch: Orchestrator, engine: Engine) -> None:
    # TC-0066 (AC-US-00-012-5)
    r = reply(orch, draft(engine), "Noted.")

    assert r.classification.confidence < 0.75
    assert r.run.outcome == "ESCALATED"
    assert (
        one(
            engine,
            "SELECT count(*) FROM escalations WHERE customer_id = CAST(:c AS uuid) "
            "AND kind = 'low_confidence'",
            c=ABC,
        )
        == 1
    )
    assert (
        one(
            engine,
            "SELECT count(*) FROM promises WHERE customer_id = CAST(:c AS uuid) AND status = 'pending'",
            c=ABC,
        )
        == 0
    )


def test_resolving_a_dispute_resumes_reminders(api: TestClient, engine: Engine) -> None:
    # TC-0082 (AC-US-00-016-5)
    reg = build_registry(engine)
    d = reg.invoke(
        "log_dispute",
        {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "short supply"},
        ToolContext(actor="ai", source="agent"),
    )["data"]

    r = api.post(
        f"/api/v1/disputes/{d['id']}/resolve", json={"note": "Credit note issued"}, headers=COLLECTOR
    )

    assert r.json()["status"] == "resolved"
    assert one(engine, "SELECT status FROM invoices WHERE number = 'INV-1047'") == "unpaid"
    msg = api.get(f"/api/v1/messages/{draft(engine)}", headers=VIEWER).json()
    assert "INV-1047" in msg["invoice_numbers"]


# --- payments ---------------------------------------------------------------------------------------------
def test_a_claim_matching_a_ledger_payment_is_matched_not_recorded_again(
    api: TestClient, orch: Orchestrator, engine: Engine
) -> None:
    # TC-0086 (AC-US-00-018-1)
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        headers=ADMIN,
        json={"customer_id": ABC, "amount_paise": 50_000_000, "reference": "NEFT ABC Distributors"},
    )
    before = one(engine, "SELECT count(*) FROM payments")

    r = reply(orch, draft(engine), "We already paid ₹5 lakh on 28 Sep, please check.")

    assert r.classification.klass == "PAYMENT_CONFIRMATION"
    assert r.run.outcome == "NO_ACTION"
    assert one(engine, "SELECT count(*) FROM payments") == before
    assert (
        one(
            engine,
            "SELECT count(*) FROM escalations WHERE customer_id = CAST(:c AS uuid) "
            "AND kind = 'claim_not_found'",
            c=ABC,
        )
        == 0
    )


def test_an_overpayment_keeps_the_excess_unallocated_and_flags_it(settings: Settings, engine: Engine) -> None:
    # TC-0091 (AC-US-00-019-3)
    credit = payments.BankCredit(
        event_id="over-1", amount_paise=80_000_000, reference="NEFT ABC Distributors"
    )
    with Session(bind=engine) as s, s.begin():
        p = payments.receive_credit(s, credit)

    assert sum(a.amount_paise for a in p.allocations) == 75_000_000
    assert one(engine, "SELECT min(remaining_paise) FROM invoice_balances") == 0
    assert one(engine, "SELECT count(*) FROM escalations WHERE payment_id = CAST(:p AS uuid)", p=p.id) == 1


def test_a_short_payment_by_the_date_partially_fulfils_the_promise(api: TestClient, engine: Engine) -> None:
    # TC-0096 (AC-US-00-020-2)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO promises (customer_id, amount_paise, promised_date) "
                "VALUES (CAST(:c AS uuid), 30000000, '2026-10-05')"
            ),
            {"c": ABC},
        )
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        headers=ADMIN,
        json={"customer_id": ABC, "amount_paise": 10_000_000, "reference": "NEFT ABC Distributors"},
    )

    api.post("/api/v1/admin/clock/advance", json={"days": 6}, headers=ADMIN)

    [p] = api.get(
        "/api/v1/promises",
        params={"filter[customer_id]": ABC, "filter[status]": "partially_fulfilled"},
        headers=VIEWER,
    ).json()["data"]
    assert p["promised_date"] == "2026-10-05"


def test_a_credit_writes_payment_received_and_matched_events(api: TestClient) -> None:
    # TC-0083 (AC-US-00-017-1)
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        headers=ADMIN,
        json={"customer_id": ABC, "amount_paise": 30_000_000, "reference": "NEFT ABC Distributors"},
    )

    kinds = [e["kind"] for e in api.get(f"/api/v1/customers/{ABC}/timeline", headers=VIEWER).json()["data"]]

    assert "payment_received" in kinds and "payment_matched" in kinds


def test_an_ambiguous_credit_is_on_the_attention_list(api: TestClient) -> None:
    # TC-0084 (AC-US-00-017-2)
    body = (
        b'{"event_id":"amb-1","amount_paise":100000,"reference":"payment","payer_name":"","occurred_at":""}'
    )
    ts, sig, raw = payments.signed_credit(
        api.app.state.settings.bank_webhook_secret,  # type: ignore[attr-defined]
        payments.BankCredit.model_validate_json(body),
    )
    api.post("/api/v1/webhooks/bank", content=raw, headers={"X-Bank-Timestamp": ts, "X-Bank-Signature": sig})

    pending = api.get("/api/v1/dashboard", headers=VIEWER).json()["attention"]["needs_verification"]

    assert [p["amount_paise"] for p in pending] == [100000]


# --- schedule ---------------------------------------------------------------------------------------------
def test_the_daily_run_is_queued_once_per_demo_date(api: TestClient, engine: Engine) -> None:
    # TC-0024 (AC-US-01-001-7)
    early = datetime(2026, 9, 30, 8, 59, tzinfo=IST)
    nine = datetime(2026, 9, 30, 9, 0, tzinfo=IST).astimezone(UTC)
    with engine.begin() as c:
        c.execute(text("DELETE FROM jobs"))

    schedule(engine, early)
    none_yet = one(engine, "SELECT count(*) FROM jobs")
    schedule(engine, nine)
    schedule(engine, nine)
    run_now = api.post("/api/v1/runs", json={}, headers=ADMIN).json()

    assert none_yet == 0
    assert one(engine, "SELECT count(*) FROM jobs WHERE kind = 'daily_run'") == 1
    assert one(engine, "SELECT count(*) FROM jobs WHERE kind = 'promise_check'") == 1
    assert (run_now["run_date"], run_now["queued"]) == (str(date(2026, 9, 30)), False)


# --- roles ------------------------------------------------------------------------------------------------
SPEC = yaml.safe_load(
    (find_up("api", Path(__file__).parents[2]) / "openapi.yaml").read_text(encoding="utf-8")
)
OPS = [
    (m, p, o["x-roles"])
    for p, ops in SPEC["paths"].items()
    for m, o in ops.items()
    if not str(o["x-roles"]).startswith(
        ("public", "bank feed", "cron secret")
    )  # the webhook and cron have no role; HMAC and CRON_SECRET are tested apart
]


def test_each_role_signs_in_as_itself(api: TestClient) -> None:
    # TC-0112 (AC-US-01-007-1)
    for role in ("admin", "collector", "viewer"):
        assert api.get("/api/v1/auth/me", headers={"X-Demo-Role": role}).json()["role"] == role


@pytest.mark.parametrize(("method", "path", "roles"), OPS, ids=[f"{m} {p}" for m, p, _ in OPS])
def test_role_matrix(api: TestClient, method: str, path: str, roles: str) -> None:
    # TC-0113 (AC-US-01-007-2), TC-0114 (AC-US-01-007-3): no role is 401; a role outside x-roles is 403
    url = "/api/v1" + path.replace("{id}", str(uid("none", path))).replace("{number}", "INV-1034")
    allowed = {r.strip() for r in roles.split(",")}

    anonymous = api.request(method, url)
    results = {
        r: api.request(method, url, headers={"X-Demo-Role": r}).status_code
        for r in ("viewer", "collector", "admin")
    }

    assert anonymous.status_code == 401
    for role, status in results.items():
        assert (status == 403) == (role not in allowed), (role, status)


def test_an_unknown_run_id_is_404_not_500(api: TestClient) -> None:
    # Audit finding 11
    r = api.get(f"/api/v1/runs/{uid('none', 'run')}", headers={"X-Demo-Role": "viewer"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
