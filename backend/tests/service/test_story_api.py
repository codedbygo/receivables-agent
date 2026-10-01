"""The ABC demo story (REQ-110, brief 4.24) end to end over HTTP, plus roles and the kill switch on the API."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.main import create_app
from app.channels.email import Outbound
from app.core.config import Settings
from app.services import approval
from app.services.demo import reset_demo, uid
from app.worker.jobs import Defer

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
SECRET = "story-bank-secret"  # noqa: S105  test value


class Inbox:
    name = "email"

    def __init__(self) -> None:
        self.sent: list[Outbound] = []

    def send(self, message: Outbound) -> str:
        self.sent.append(message)
        return "ok"


@pytest.fixture
def settings(engine: Engine) -> Settings:
    s = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay", bank_webhook_secret=SECRET)
    reset_demo(engine, s)
    return s


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def as_(role: str) -> dict[str, str]:
    return {"X-Demo-Role": role}


def outstanding(api: TestClient) -> int:
    return int(api.get(f"/api/v1/customers/{ABC}", headers=as_("viewer")).json()["outstanding_paise"])


# TC-0202 (AC-US-03-001-1), TC-0234 (AC-US-01-005-3), TC-0235 (AC-US-01-005-4)
def test_abc_story_from_reminder_to_escalation(api: TestClient, engine: Engine) -> None:
    admin, collector = as_("admin"), as_("collector")
    assert outstanding(api) == 75_000_000

    run = api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=admin)
    assert run.status_code == 202, run.text
    run_id = run.json()["run_ids"][0]
    steps = api.get(f"/api/v1/runs/{run_id}", headers=collector).json()
    assert steps["outcome"] == "WAIT_FOR_APPROVAL"
    assert steps["tool_call_count"] <= 4

    [draft] = api.get(
        "/api/v1/messages",
        params={"filter[status]": "pending_approval", "filter[customer_id]": ABC},
        headers=collector,
    ).json()["data"]
    assert draft["verified"] and "₹7,50,000" in draft["body"]
    ok = api.post(
        f"/api/v1/messages/{draft['id']}/approve", headers={**collector, "If-Match": str(draft["version"])}
    )
    assert ok.json()["status"] == "approved"

    inbox = Inbox()
    approval.deliver(engine, draft["id"], {"email": inbox})
    assert (
        inbox.sent
        and api.get(f"/api/v1/messages/{draft['id']}", headers=collector).json()["status"] == "sent"
    )

    reply = api.post(
        "/api/v1/replies",
        json={
            "message_id": draft["id"],
            "body": "We can pay ₹3 lakh on October 5 and the remaining amount later.",
        },
        headers=collector,
    ).json()
    assert (reply["classification"], reply["amount_paise"], reply["stated_date"]) == (
        "PROMISE",
        30_000_000,
        "2026-10-05",
    )
    [promise] = api.get(
        "/api/v1/promises",
        params={"filter[customer_id]": ABC, "filter[status]": "pending"},
        headers=collector,
    ).json()["data"]

    assert (
        api.post("/api/v1/admin/clock/advance", json={"days": 5}, headers=admin).json()["demo_today"]
        == "2026-10-05"
    )
    credit = api.post(
        "/api/v1/admin/simulate/bank-credit",
        json={"customer_id": ABC, "amount_paise": 30_000_000, "reference": "NEFT ABC Distributors UTR 4411"},
        headers=admin,
    ).json()
    assert credit["match_status"] == "matched"
    assert outstanding(api) == 45_000_000
    check = api.post(f"/api/v1/promises/{promise['id']}/check-payment", headers=collector).json()
    assert check["promise"]["status"] == "fulfilled" and check["matched_payment_ids"] == [credit["id"]]

    dispute = api.post(
        "/api/v1/replies",
        json={
            "message_id": draft["id"],
            "body": "INV-1047 was billed for 50 units but we received only 40. Please correct it.",
        },
        headers=collector,
    ).json()
    assert dispute["classification"] == "DISPUTE"
    # HACK-001: a dispute run also drafts an acknowledgement, but the escalation decides the outcome (HLD Flow B).
    assert (
        api.get(f"/api/v1/runs/{dispute['agent_run_id']}", headers=collector).json()["outcome"] == "ESCALATED"
    )
    assert (
        api.get("/api/v1/disputes", params={"filter[customer_id]": ABC}, headers=collector).json()["data"][0][
            "invoice_number"
        ]
        == "INV-1047"
    )
    assert api.get(
        "/api/v1/escalations",
        params={"filter[customer_id]": ABC, "filter[status]": "open"},
        headers=collector,
    ).json()["data"]

    kinds = {
        e["kind"] for e in api.get(f"/api/v1/customers/{ABC}/timeline", headers=collector).json()["data"]
    }
    # TC-0094 (AC-US-00-022-1): every event kind the story must leave behind
    assert {
        "invoice_due",
        "reminder_drafted",
        "guardrail_passed",
        "approved",
        "sent",
        "reply_received",
        "classified",
        "promise_logged",
        "payment_received",
        "payment_matched",
        "promise_fulfilled",
        "dispute_opened",
        "escalation_created",
    } <= kinds, kinds
    assert api.get("/api/v1/dashboard", headers=as_("viewer")).json()["open_disputes"] >= 1


def test_roles_are_enforced(api: TestClient) -> None:
    assert api.get("/api/v1/customers").status_code == 401
    assert api.get("/api/v1/auth/me", headers=as_("viewer")).json()["role"] == "viewer"
    assert api.post("/api/v1/runs", json={}, headers=as_("collector")).status_code == 403
    assert (
        api.patch(
            "/api/v1/admin/settings", json={"sending_enabled": False}, headers=as_("viewer")
        ).status_code
        == 403
    )


def test_kill_switch_blocks_the_send_and_edit_is_reverified(api: TestClient, engine: Engine) -> None:
    admin, collector = as_("admin"), as_("collector")
    api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=admin)
    [draft] = api.get(
        "/api/v1/messages", params={"filter[status]": "pending_approval"}, headers=collector
    ).json()["data"]

    bad = draft["body"].replace("₹7,50,000", "₹5,00,000")
    r = api.patch(
        f"/api/v1/messages/{draft['id']}",
        json={"subject": draft["subject"], "body": bad},
        headers={**collector, "If-Match": str(draft["version"])},
    )
    assert r.status_code >= 400 and r.json()["error"]["code"] in {
        "TOTAL_MISMATCH",
        "AMOUNT_MISMATCH",
        "INVENTED_AMOUNT",
    }
    stale = api.post(f"/api/v1/messages/{draft['id']}/approve", headers={**collector, "If-Match": "999"})
    assert stale.json()["error"]["code"] == "STALE_DRAFT"

    assert (
        api.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=admin).json()[
            "sending_enabled"
        ]
        is False
    )
    api.post(
        f"/api/v1/messages/{draft['id']}/approve", headers={**collector, "If-Match": str(draft["version"])}
    )
    inbox = Inbox()
    with pytest.raises(Defer):
        approval.deliver(engine, draft["id"], {"email": inbox})
    assert inbox.sent == []


def test_webhook_rejects_a_bad_signature(api: TestClient) -> None:
    body = b'{"event_id":"x1","amount_paise":100,"reference":"r","payer_name":"","occurred_at":""}'
    r = api.post(
        "/api/v1/webhooks/bank", content=body, headers={"X-Bank-Timestamp": "1", "X-Bank-Signature": "00"}
    )
    assert r.json()["error"]["code"] == "SIGNATURE_INVALID"


def test_webhook_rejects_a_malformed_signature_and_an_oversized_body(api: TestClient) -> None:
    # Security review 2026-10-01: a non-ASCII signature was a 500; the body had no size limit.
    h = {"X-Bank-Timestamp": "1", "X-Bank-Signature": "é".encode("latin-1")}
    odd = api.post("/api/v1/webhooks/bank", content=b"{}", headers=h)
    big = api.post("/api/v1/webhooks/bank", content=b"x" * 70_000, headers={**h, "X-Bank-Signature": "00"})

    assert odd.json()["error"]["code"] == "SIGNATURE_INVALID"
    assert big.json()["error"]["code"] == "VALIDATION_ERROR"


# TC-0269 (AC-US-00-023-2)
def test_dashboard_money_is_integer_paise(api: TestClient) -> None:
    # HACK-001: SUM(bigint) is numeric in Postgres; the dashboard returned money as strings.
    d = api.get("/api/v1/dashboard", headers=as_("viewer")).json()

    money = [d["total_outstanding_paise"], d["total_overdue_paise"], *d["ageing"].values()]
    assert all(isinstance(v, int) for v in money), money
