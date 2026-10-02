"""Dashboard, next action, timeline and clock (US-00-003, US-00-004, US-00-021, US-01-004, US-01-006, US-01-016)."""

import os
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo, uid

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
KUMAR = uid("customer", "Kumar Electricals")
EASTERN = uid("customer", "Eastern Electricals")
VIEWER = {"X-Demo-Role": "viewer"}
COLLECTOR = {"X-Demo-Role": "collector"}
ADMIN = {"X-Demo-Role": "admin"}


@pytest.fixture
def settings(engine: Engine) -> Settings:
    s = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, s)
    return s


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql), {"d": date(2026, 9, 30)}).scalar()


def test_dashboard_totals_equal_direct_queries(api: TestClient, engine: Engine) -> None:
    # TC-0011 (AC-US-00-003-1)
    d = api.get("/api/v1/dashboard", headers=VIEWER).json()

    balances = "FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id WHERE b.remaining_paise > 0"
    assert d["total_outstanding_paise"] == scalar(engine, f"SELECT SUM(b.remaining_paise) {balances}")
    assert d["total_overdue_paise"] == scalar(
        engine, f"SELECT SUM(b.remaining_paise) {balances} AND i.due_date < :d"
    )
    assert d["customers_overdue"] == scalar(
        engine, f"SELECT count(DISTINCT i.customer_id) {balances} AND i.due_date < :d"
    )
    assert d["missed_promises"] == scalar(engine, "SELECT count(*) FROM promises WHERE status = 'missed'")
    assert d["open_disputes"] == scalar(engine, "SELECT count(*) FROM disputes WHERE status = 'open'")
    assert d["pending_approvals"] == scalar(
        engine, "SELECT count(*) FROM messages WHERE status = 'pending_approval'"
    )
    assert d["todays_promises"] == scalar(
        engine, "SELECT count(*) FROM promises WHERE status = 'pending' AND promised_date = :d"
    )
    assert d["open_escalations"] == scalar(engine, "SELECT count(*) FROM escalations WHERE status = 'open'")


def test_ageing_buckets_split_exactly_at_their_edges(api: TestClient, engine: Engine) -> None:
    # TC-0012 (AC-US-00-003-2)
    today = date(2026, 9, 30)
    with engine.begin() as c:
        c.execute(text("UPDATE invoices SET due_date = :far"), {"far": today + timedelta(days=400)})
        free = (
            c.execute(
                text("""SELECT number FROM invoices i WHERE NOT EXISTS
            (SELECT 1 FROM payment_allocations a WHERE a.invoice_id = i.id) ORDER BY number LIMIT 7""")
            )
            .scalars()
            .all()
        )
        for k, (number, days) in enumerate(zip(free, (0, 30, 31, 60, 61, 90, 91), strict=True)):
            c.execute(
                text(
                    "UPDATE invoices SET invoice_date = :due - 30, due_date = :due, amount_paise = :a WHERE number = :n"
                ),
                {"due": today - timedelta(days=days), "a": 10 ** (k + 2), "n": number},
            )

    a = api.get("/api/v1/dashboard", headers=VIEWER).json()["ageing"]

    assert a == {
        "d0_30_paise": 10**2 + 10**3,
        "d31_60_paise": 10**4 + 10**5,
        "d61_90_paise": 10**6 + 10**7,
        "d90_plus_paise": 10**8,
    }


def test_attention_groups_each_link_their_customer(api: TestClient) -> None:
    # TC-0013 (AC-US-00-003-3)
    api.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=ADMIN)
    api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN)
    [m] = api.get("/api/v1/messages", params={"filter[customer_id]": ABC}, headers=COLLECTOR).json()["data"]
    api.post(f"/api/v1/messages/{m['id']}/approve", headers={**COLLECTOR, "If-Match": str(m["version"])})

    a = api.get("/api/v1/dashboard", headers=VIEWER).json()["attention"]

    for group in ("high_priority", "missed_promises", "disputes", "approved_ready"):
        assert a[group] and all(row["customer_id"] for row in a[group]), group


def test_next_action_for_a_missed_promise_is_a_follow_up(api: TestClient) -> None:
    # TC-0016 (AC-US-00-004-2)
    t = api.get(f"/api/v1/customers/{KUMAR}/timeline", headers=VIEWER).json()

    assert t["next_action"] == "Send follow-up on missed promise"


def test_next_action_for_an_open_dispute_is_to_resolve_it(api: TestClient) -> None:
    # TC-0017 (AC-US-00-004-3)
    t = api.get(f"/api/v1/customers/{EASTERN}/timeline", headers=VIEWER).json()

    assert t["next_action"] == "Resolve dispute"


def test_advancing_the_clock_is_on_the_timeline_of_customers_with_promises(
    api: TestClient, engine: Engine
) -> None:
    # TC-0103 (AC-US-01-004-3)
    with engine.begin() as c:
        c.execute(
            text(
                """INSERT INTO promises (customer_id, amount_paise, promised_date) VALUES (CAST(:c AS uuid), 100, :p)"""
            ),
            {"c": ABC, "p": date(2026, 10, 3)},
        )

    out = api.post("/api/v1/admin/clock/advance", json={"days": 5}, headers=ADMIN).json()

    assert out["demo_today"] == "2026-10-05"
    kinds = [e["kind"] for e in api.get(f"/api/v1/customers/{ABC}/timeline", headers=VIEWER).json()["data"]]
    assert "clock_advanced" in kinds and "promise_missed" in kinds
    days = api.get(f"/api/v1/customers/{ABC}/invoices", headers=VIEWER).json()["data"]
    assert next(i for i in days if i["number"] == "INV-1021")["days_overdue"] == 24


def test_kill_switch_survives_an_api_restart(settings: Settings) -> None:
    # TC-0109 (AC-US-01-006-1)
    with TestClient(create_app(settings)) as first:
        first.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=ADMIN)

    with TestClient(create_app(settings)) as second:
        s = second.get("/api/v1/admin/settings", headers=VIEWER).json()

    assert s["sending_enabled"] is False


def test_only_an_admin_changes_settings(api: TestClient) -> None:
    # TC-0111 (AC-US-01-006-3)
    for role in ("viewer", "collector"):
        r = api.patch(
            "/api/v1/admin/settings", json={"sending_enabled": False}, headers={"X-Demo-Role": role}
        )
        assert r.status_code == 403, role


def test_fresh_install_is_manual_mode(api: TestClient) -> None:
    # TC-0158 (AC-US-01-016-1)
    assert api.get("/api/v1/admin/settings", headers=VIEWER).json()["autonomy_mode"] == "manual"


def test_assisted_mode_approves_every_verified_draft_in_one_action(api: TestClient) -> None:
    # TC-0159 (AC-US-01-016-2)
    ids = [p["customer_id"] for p in api.get("/api/v1/priorities", headers=VIEWER).json()["data"][:5]]
    api.post("/api/v1/runs", json={"customer_ids": ids}, headers=ADMIN)
    drafts = api.get(
        "/api/v1/messages", params={"filter[status]": "pending_approval"}, headers=COLLECTOR
    ).json()["data"]
    refused = api.post(
        "/api/v1/messages/approve-batch",
        json={"messages": [{"id": d["id"], "version": d["version"]} for d in drafts]},
        headers=COLLECTOR,
    )
    api.patch("/api/v1/admin/settings", json={"autonomy_mode": "assisted"}, headers=ADMIN)

    done = api.post(
        "/api/v1/messages/approve-batch",
        json={"messages": [{"id": d["id"], "version": d["version"]} for d in drafts]},
        headers=COLLECTOR,
    )

    assert len(drafts) == 5
    assert refused.json()["error"]["code"] == "FEATURE_DISABLED"
    assert [m["status"] for m in done.json()["data"]] == ["approved"] * 5
    for d in drafts:
        kinds = [
            e["kind"]
            for e in api.get(f"/api/v1/customers/{d['customer_id']}/timeline", headers=VIEWER).json()["data"]
        ]
        assert kinds.count("approved") == 1


def test_todays_promises_list_and_check_payment(api: TestClient, engine: Engine) -> None:
    # TC-0092 (AC-US-00-021-1), TC-0093 (AC-US-00-021-2)
    with engine.begin() as c:
        pid = c.execute(
            text("""INSERT INTO promises (customer_id, amount_paise, promised_date)
            VALUES (CAST(:c AS uuid), 30000000, '2026-10-05') RETURNING id::text"""),
            {"c": ABC},
        ).scalar_one()
    api.post("/api/v1/admin/clock/advance", json={"days": 5}, headers=ADMIN)

    [row] = api.get("/api/v1/dashboard", headers=VIEWER).json()["attention"]["todays_promises"]
    before = api.post(f"/api/v1/promises/{pid}/check-payment", headers=COLLECTOR).json()
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        json={"customer_id": ABC, "amount_paise": 30000000, "reference": "NEFT ABC Distributors"},
        headers=ADMIN,
    )
    after = api.post(f"/api/v1/promises/{pid}/check-payment", headers=COLLECTOR).json()

    assert (row["customer_name"], row["amount_paise"]) == ("ABC Distributors", 30000000)
    assert (before["promise"]["status"], before["message"]) == ("pending", "No matching payment yet")
    assert after["promise"]["status"] == "fulfilled"


def test_batch_approval_refuses_a_draft_that_changed_after_it_was_shown(api: TestClient) -> None:
    # Security audit finding 6: a draft rewritten after the collector saw it is never approved unseen.
    ids = [p["customer_id"] for p in api.get("/api/v1/priorities", headers=VIEWER).json()["data"][:2]]
    api.post("/api/v1/runs", json={"customer_ids": ids}, headers=ADMIN)
    api.patch("/api/v1/admin/settings", json={"autonomy_mode": "assisted"}, headers=ADMIN)
    shown = api.get(
        "/api/v1/messages", params={"filter[status]": "pending_approval"}, headers=COLLECTOR
    ).json()["data"]
    first = shown[0]
    api.patch(
        f"/api/v1/messages/{first['id']}",
        json={"subject": first["subject"], "body": first["body"] + "\n\nThank you."},
        headers={**COLLECTOR, "If-Match": str(first["version"])},
    )

    r = api.post(
        "/api/v1/messages/approve-batch",
        json={"messages": [{"id": d["id"], "version": d["version"]} for d in shown]},
        headers=COLLECTOR,
    )

    assert r.json()["error"]["code"] == "STALE_DRAFT"
    statuses = {
        m["status"]
        for m in api.get("/api/v1/messages", params={"filter[status]": "approved"}, headers=COLLECTOR).json()[
            "data"
        ]
    }
    assert statuses == set()  # nothing in the batch was approved
