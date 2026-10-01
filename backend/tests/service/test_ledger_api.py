"""US-00-001, US-00-002 over HTTP against the seeded database."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo, uid

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")


@pytest.fixture(scope="module")
def client(engine: Engine) -> TestClient:
    settings = Settings(database_url=os.environ["DATABASE_URL"])
    reset_demo(engine, settings)
    return TestClient(create_app(settings), headers={"X-Demo-Role": "viewer"})


# TC-0160 (AC-US-00-001-1)
def test_abc_unpaid_invoices_with_balances_and_days_overdue(client: TestClient) -> None:
    r = client.get(f"/api/v1/customers/{ABC}/invoices", params={"filter[status]": "unpaid"})

    assert r.status_code == 200
    rows = [
        (i["number"], i["amount_paise"], i["remaining_paise"], i["days_overdue"]) for i in r.json()["data"]
    ]
    assert rows == [
        ("INV-1021", 40_000_000, 40_000_000, 19),
        ("INV-1034", 20_000_000, 20_000_000, 12),
        ("INV-1047", 15_000_000, 15_000_000, 5),
    ]


# TC-0161 (AC-US-00-001-2), TC-0162 (AC-US-00-001-3)
def test_customer_outstanding_is_derived_from_the_ledger(client: TestClient) -> None:
    c = client.get(f"/api/v1/customers/{ABC}").json()

    assert (c["name"], c["outstanding_paise"], c["overdue_paise"], c["band"]) == (
        "ABC Distributors",
        75_000_000,
        75_000_000,
        "HIGH",
    )
    assert set(c) >= {"email", "phone", "segment", "credit_terms_days"}


# TC-0163 (AC-US-00-001-6)
def test_days_overdue_follow_the_demo_clock(client: TestClient, engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE settings SET demo_today = DATE '2026-10-05'"))
    try:
        rows = client.get(f"/api/v1/customers/{ABC}/invoices").json()["data"]
        assert next(i for i in rows if i["number"] == "INV-1021")["days_overdue"] == 24
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE settings SET demo_today = DATE '2026-09-30'"))


# TC-0166 (AC-US-00-002-3)
def test_abc_priority_explains_itself(client: TestClient) -> None:
    p = client.get(f"/api/v1/customers/{ABC}/priority").json()

    assert (p["score"], p["band"]) == (66, "HIGH")
    assert [r["text"] for r in p["reasons"]][:3] == [
        "High outstanding (₹7,50,000)",
        "Oldest invoice 19 days overdue",
        "1 missed promise",
    ]


# TC-0165 (AC-US-00-002-2)
def test_top_15_is_stable_and_contains_abc(client: TestClient) -> None:
    first = client.get("/api/v1/priorities").json()["data"]
    second = client.get("/api/v1/priorities").json()["data"]

    assert len(first) == 15
    assert [p["customer_id"] for p in first] == [p["customer_id"] for p in second]
    assert ABC in [p["customer_id"] for p in first]
    assert all(p["score"] > 0 for p in first)


def test_unknown_customer_is_404_with_the_envelope(client: TestClient) -> None:
    r = client.get(f"/api/v1/customers/{uid('customer', 'nobody')}")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_customers_list_has_all_50(client: TestClient) -> None:
    assert len(client.get("/api/v1/customers").json()["data"]) == 50
