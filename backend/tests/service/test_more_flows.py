"""Flows with no test until the coverage pass of 2026-10-02: reject, resend, a collector matching an ambiguous
credit, resolving an escalation, the promise-check job, and replies that need a human."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.api.main import create_app
from app.core.config import Settings
from app.services import payments
from app.services.demo import reset_demo, uid

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
ADMIN, COLLECTOR = {"X-Demo-Role": "admin"}, {"X-Demo-Role": "collector"}
SECRET = "test-bank-secret"


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    settings = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, settings)
    with TestClient(create_app(settings)) as c:
        yield c


def one(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def abc_draft(api: TestClient) -> dict[str, object]:
    assert api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN).status_code == 202
    page = api.get(
        "/api/v1/messages",
        params={"filter[customer_id]": ABC, "filter[status]": "pending_approval"},
        headers=COLLECTOR,
    ).json()
    draft: dict[str, object] = page["data"][0]
    return draft


def test_a_rejected_draft_needs_a_reason_and_is_rejected_once(api: TestClient, engine: Engine) -> None:
    m = abc_draft(api)
    url = f"/api/v1/messages/{m['id']}/reject"

    blank = api.post(url, json={"reason": "   "}, headers=COLLECTOR)
    done = api.post(url, json={"reason": "Tone too firm for a first reminder"}, headers=COLLECTOR)
    again = api.post(url, json={"reason": "again"}, headers=COLLECTOR)

    assert blank.json()["error"]["code"] == "REASON_REQUIRED"
    assert done.json()["status"] == "rejected"
    assert again.json()["error"]["code"] == "NOT_APPROVED"
    assert (
        one(engine, f"SELECT count(*) FROM timeline_events WHERE kind = 'rejected' AND ref_id = '{m['id']}'")
        == 1
    )


def test_only_a_failed_message_can_be_resent_and_resending_requeues_it(
    api: TestClient, engine: Engine
) -> None:
    m = abc_draft(api)
    url = f"/api/v1/messages/{m['id']}/resend"
    pending = api.post(url, headers=COLLECTOR)
    with engine.begin() as c:
        c.execute(
            text(f"UPDATE messages SET status = 'failed', last_error = 'smtp down' WHERE id = '{m['id']}'")
        )

    resent = api.post(url, headers=COLLECTOR)

    assert pending.json()["error"]["code"] == "NOT_APPROVED"
    assert resent.json()["status"] == "approved"
    assert (
        one(engine, f"SELECT count(*) FROM jobs WHERE kind = 'send_message' AND dedupe_key = '{m['id']}'")
        == 1
    )


def test_a_collector_matches_an_ambiguous_credit_once(api: TestClient, engine: Engine) -> None:
    ts, sig, body = payments.signed_credit(
        SECRET,
        payments.BankCredit(event_id="evt-amb", amount_paise=10_000_000, reference="PAYMENT FROM TRADERS"),
    )
    payments.verify_signature(SECRET, ts, sig, body)
    with Session(bind=engine) as s, s.begin():
        pid = payments.receive_credit(s, payments.BankCredit.model_validate_json(body)).id

    matched = api.post(f"/api/v1/payments/{pid}/match", json={"customer_id": ABC}, headers=COLLECTOR)
    twice = api.post(f"/api/v1/payments/{pid}/match", json={"customer_id": ABC}, headers=COLLECTOR)
    unknown = api.post(
        f"/api/v1/payments/{uid('none', 'pay')}/match", json={"customer_id": ABC}, headers=COLLECTOR
    )

    assert matched.json()["match_status"] == "matched" and matched.json()["allocations"]
    assert twice.json()["error"]["code"] == "VALIDATION_ERROR"
    assert unknown.status_code == 404


def test_resolving_an_escalation_closes_it_once(api: TestClient, engine: Engine) -> None:
    eid = one(engine, "SELECT id::text FROM escalations WHERE status = 'open' LIMIT 1")
    url = f"/api/v1/escalations/{eid}/resolve"

    first = api.post(url, json={"note": "Called the customer, corrected"}, headers=COLLECTOR)
    second = api.post(url, json={"note": "again"}, headers=COLLECTOR)
    unknown = api.post(
        f"/api/v1/escalations/{uid('none', 'esc')}/resolve", json={"note": "x"}, headers=COLLECTOR
    )

    assert first.json()["status"] == "resolved" and second.json()["status"] == "resolved"
    assert (
        one(
            engine,
            f"SELECT count(*) FROM timeline_events WHERE kind = 'escalation_resolved' AND ref_id = '{eid}'",
        )
        == 1
    )
    assert unknown.status_code == 404


def test_the_promise_check_job_marks_a_promise_missed_after_its_date(api: TestClient, engine: Engine) -> None:
    with engine.begin() as c:
        c.execute(
            text(f"""INSERT INTO promises (customer_id, amount_paise, promised_date, status)
            VALUES ('{ABC}', 30000000, DATE '2026-09-29', 'pending')""")
        )

    payments.check_promises(engine)

    assert (
        one(engine, f"SELECT status FROM promises WHERE customer_id = '{ABC}' AND amount_paise = 30000000")
        == "missed"
    )


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("We will pay soon, promise.", "Promise without a clear amount or date"),
        (
            "We dispute the bill, the quantity was wrong.",
            "Dispute without an invoice number: pick the invoice",
        ),
    ],
)
def test_a_reply_missing_what_it_needs_is_escalated_to_a_human(
    api: TestClient, engine: Engine, body: str, reason: str
) -> None:
    m = abc_draft(api)
    r = api.post("/api/v1/replies", json={"message_id": m["id"], "body": body}, headers=COLLECTOR)

    assert r.status_code == 201, r.text
    assert one(engine, f"SELECT count(*) FROM escalations WHERE reason = '{reason}'") == 1
