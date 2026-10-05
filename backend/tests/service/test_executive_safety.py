"""HACK-003 F8 and the AI Safety Center: every figure equals a direct query over the ledger and event log."""

import os
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo, uid

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
VIEWER = {"X-Demo-Role": "viewer"}
COLLECTOR = {"X-Demo-Role": "collector"}
ADMIN = {"X-Demo-Role": "admin"}


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    s = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, s)
    with TestClient(create_app(s)) as c:
        yield c


def scalar(engine: Engine, sql: str) -> int:
    with engine.connect() as c:
        return int(c.execute(text(sql), {"d": date(2026, 9, 30)}).scalar() or 0)


def test_executive_kpis_equal_direct_queries(api: TestClient, engine: Engine) -> None:
    e = api.get("/api/v1/executive", headers=VIEWER).json()
    k = e["kpis"]

    assert k["total_receivables_paise"] == scalar(engine, "SELECT SUM(remaining_paise) FROM invoice_balances")
    assert k["overdue_paise"] == scalar(
        engine,
        "SELECT SUM(b.remaining_paise) FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id "
        "WHERE i.due_date < :d",
    )
    assert k["missed_promises_paise"] == scalar(
        engine, "SELECT SUM(amount_paise) FROM promises WHERE status = 'missed'"
    )
    assert set(e["definitions"]) >= {"total_receivables", "at_risk", "collection_rate"}
    assert sum(p["value"] for p in e["ageing"]) == k["total_receivables_paise"]
    assert len(e["collections_by_week"]) == 8
    assert len(e["overdue_trend"]) == 8


def test_a_bank_credit_moves_collected_this_month(api: TestClient) -> None:
    before = api.get("/api/v1/executive", headers=VIEWER).json()["kpis"]["collected_this_month_paise"]
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        json={"customer_id": ABC, "amount_paise": 30_000_000, "reference": "NEFT ABC Distributors UTR 9"},
        headers=ADMIN,
    )
    after = api.get("/api/v1/executive", headers=VIEWER).json()["kpis"]

    assert after["collected_this_month_paise"] == before + 30_000_000
    assert after["collection_rate_pct"] is not None


def test_every_attention_item_carries_its_factors(api: TestClient) -> None:
    items = api.get("/api/v1/executive", headers=VIEWER).json()["attention"]

    assert items
    abc = next(i for i in items if i["customer_name"] == "ABC Distributors")
    assert abc["severity"] == "red"
    assert all(i["factors"] for i in items)


def test_a_refused_edit_is_counted_as_a_blocked_amount(api: TestClient) -> None:
    before = api.get("/api/v1/safety", headers=VIEWER).json()
    api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN)
    [draft] = api.get(
        "/api/v1/messages", params={"filter[status]": "pending_approval"}, headers=COLLECTOR
    ).json()["data"]
    r = api.patch(
        f"/api/v1/messages/{draft['id']}",
        json={"subject": draft["subject"], "body": draft["body"].replace("₹7,50,000", "₹5,00,000")},
        headers={**COLLECTOR, "If-Match": str(draft["version"])},
    )
    after = api.get("/api/v1/safety", headers=VIEWER).json()

    assert r.status_code >= 400
    assert after["incorrect_amounts_blocked"] > before["incorrect_amounts_blocked"]
    assert after["messages_checked"] == before["messages_checked"] + 1
    assert after["automatic_sends"] == 0
    assert after["kill_switch"].startswith("READY")


def test_the_safety_center_reflects_the_kill_switch(api: TestClient) -> None:
    api.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=ADMIN)

    assert api.get("/api/v1/safety", headers=VIEWER).json()["kill_switch"].startswith("ENGAGED")


def test_both_views_need_a_signed_in_role(api: TestClient) -> None:
    assert api.get("/api/v1/executive").status_code == 401
    assert api.get("/api/v1/safety").status_code == 401
