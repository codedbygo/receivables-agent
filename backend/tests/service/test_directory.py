"""HACK-007 distributor and invoice management over HTTP against Postgres: create, edit, delete, add an invoice,
CSV upload, and who may do each."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry

pytestmark = pytest.mark.integration
METRO = uid("customer", "Metro Wholesale")
EASTERN = uid("customer", "Eastern Electricals")
KUMAR = uid("customer", "Kumar Electricals")
VIEWER = {"X-Demo-Role": "viewer"}
COLLECTOR = {"X-Demo-Role": "collector"}
ADMIN = {"X-Demo-Role": "admin"}
RIYA = {"name": "Riya Traders", "email": "riya@example.com", "phone": "+91 98000 11111", "segment": "sme"}
INVOICE = {
    "number": "INV-5001",
    "invoice_date": "2026-09-01",
    "due_date": "2026-09-20",
    "amount_paise": 12_500_000,
}
HEADER = (
    "customer_name,email,phone,segment,credit_terms_days,invoice_number,invoice_date,due_date,amount_rupees"
)
PROSE = (
    "Dear Metro Wholesale,\n\nA gentle reminder that these invoices are now past due:\n\n{{invoice_table}}\n\n"
    "Total outstanding: {{total}}\n\nPlease let us know when we can expect payment.\n\nRegards,\nAccounts team"
)


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    s = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, s)
    with TestClient(create_app(s)) as c:
        yield c


def count(engine: Engine, sql: str, **params: object) -> int:
    with engine.connect() as c:
        return int(c.execute(text(sql), params).scalar_one())


def test_a_collector_creates_a_customer_who_starts_with_nothing_owed(api: TestClient, engine: Engine) -> None:
    r = api.post("/api/v1/customers", json=RIYA, headers=COLLECTOR)

    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["name"], c["email"], c["outstanding_paise"], c["band"]) == (
        "Riya Traders",
        "riya@example.com",
        0,
        None,
    )
    assert c["credit_terms_days"] == 30
    names = [x["name"] for x in api.get("/api/v1/customers", headers=VIEWER).json()["data"]]
    assert "Riya Traders" in names
    sql = "SELECT count(*) FROM timeline_events WHERE customer_id = CAST(:c AS uuid) AND kind = 'customer_created'"
    assert count(engine, sql, c=c["id"]) == 1


def test_a_second_customer_with_the_same_name_is_refused_whatever_the_case(api: TestClient) -> None:
    r = api.post("/api/v1/customers", json={**RIYA, "name": "metro WHOLESALE"}, headers=COLLECTOR)

    assert r.status_code == 422
    assert r.json()["error"]["message"] == "A customer named metro WHOLESALE already exists."


@pytest.mark.parametrize(
    "change",
    [
        {"name": "   "},
        {"email": "not-an-email"},
        {"segment": "huge"},
        {"credit_terms_days": 400},
        {"role": "admin"},
    ],
)
def test_a_bad_customer_is_refused(api: TestClient, change: dict[str, object]) -> None:
    r = api.post("/api/v1/customers", json={**RIYA, **change}, headers=COLLECTOR)

    assert r.status_code == 422, r.text


def test_a_viewer_cannot_create_edit_upload_or_add_an_invoice(api: TestClient) -> None:
    assert api.post("/api/v1/customers", json=RIYA, headers=VIEWER).status_code == 403
    assert api.patch(f"/api/v1/customers/{METRO}", json={"phone": "1"}, headers=VIEWER).status_code == 403
    assert api.post(f"/api/v1/customers/{METRO}/invoices", json=INVOICE, headers=VIEWER).status_code == 403
    assert api.post("/api/v1/customers/import", json={"csv": HEADER}, headers=VIEWER).status_code == 403


def test_editing_changes_only_the_fields_sent(api: TestClient, engine: Engine) -> None:
    r = api.patch(f"/api/v1/customers/{METRO}", json={"email": "ap@metro.example.com"}, headers=COLLECTOR)

    assert r.status_code == 200, r.text
    assert (r.json()["email"], r.json()["name"], r.json()["segment"]) == (
        "ap@metro.example.com",
        "Metro Wholesale",
        "sme",
    )
    sql = "SELECT summary FROM timeline_events WHERE customer_id = CAST(:c AS uuid) AND kind = 'customer_updated'"
    with engine.connect() as c:
        assert c.execute(text(sql), {"c": METRO}).scalar_one() == "Details changed: email"


def test_an_edit_refuses_another_customers_name_and_an_unknown_id(api: TestClient) -> None:
    clash = api.patch(f"/api/v1/customers/{METRO}", json={"name": "Kumar Electricals"}, headers=COLLECTOR)
    same = api.patch(f"/api/v1/customers/{METRO}", json={"name": "Metro Wholesale"}, headers=COLLECTOR)
    nobody = api.patch(
        f"/api/v1/customers/{uid('customer', 'nobody')}", json={"phone": "1"}, headers=COLLECTOR
    )
    empty = api.patch(f"/api/v1/customers/{METRO}", json={}, headers=COLLECTOR)

    assert (clash.status_code, same.status_code, nobody.status_code, empty.status_code) == (
        422,
        200,
        404,
        200,
    )


def test_an_added_invoice_is_unpaid_and_owed_in_full(api: TestClient, engine: Engine) -> None:
    cid = api.post("/api/v1/customers", json=RIYA, headers=COLLECTOR).json()["id"]

    r = api.post(f"/api/v1/customers/{cid}/invoices", json=INVOICE, headers=COLLECTOR)

    assert r.status_code == 201, r.text
    inv = r.json()
    assert (inv["number"], inv["status"], inv["remaining_paise"], inv["days_overdue"]) == (
        "INV-5001",
        "unpaid",
        12_500_000,
        10,
    )
    customer = api.get(f"/api/v1/customers/{cid}", headers=VIEWER).json()
    assert (customer["outstanding_paise"], customer["overdue_paise"]) == (12_500_000, 12_500_000)
    sql = (
        "SELECT summary FROM timeline_events WHERE customer_id = CAST(:c AS uuid) AND kind = 'invoice_added'"
    )
    with engine.connect() as c:
        assert c.execute(text(sql), {"c": cid}).scalar_one() == "INV-5001 added: ₹1,25,000 due 20 Sep 2026"


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"number": "INV-1021"}, 422),  # ABC's: numbers are unique across customers
        ({"number": "5001"}, 422),
        ({"due_date": "2026-08-01"}, 422),
        ({"amount_paise": 0}, 422),
    ],
)
def test_a_bad_invoice_is_refused(api: TestClient, change: dict[str, object], status: int) -> None:
    r = api.post(f"/api/v1/customers/{METRO}/invoices", json={**INVOICE, **change}, headers=COLLECTOR)

    assert r.status_code == status, r.text


def test_an_invoice_for_an_unknown_customer_is_404(api: TestClient) -> None:
    r = api.post(f"/api/v1/customers/{uid('customer', 'nobody')}/invoices", json=INVOICE, headers=COLLECTOR)

    assert r.status_code == 404


def test_only_an_admin_deletes_and_every_row_about_the_customer_goes(api: TestClient, engine: Engine) -> None:
    mid = build_registry(engine).invoke(
        "draft_message",
        {"customer_id": METRO, "kind": "reminder", "prose": PROSE, "tone": "gentle"},
        ToolContext("ai", "agent"),
    )["data"]["message_id"]
    assert (
        api.post(f"/api/v1/messages/{mid}/approve", headers={**COLLECTOR, "If-Match": "1"}).status_code == 200
    )
    api.post(f"/api/v1/customers/{METRO}/notes", json={"body": "Calls after 4 pm"}, headers=COLLECTOR)
    api.post(f"/api/v1/customers/{METRO}/portal-link", headers=COLLECTOR)
    queued = "SELECT count(*) FROM jobs WHERE payload->>'message_id' = :m AND status = 'queued'"
    assert count(engine, queued, m=mid) == 1

    assert api.delete(f"/api/v1/customers/{METRO}", headers=COLLECTOR).status_code == 403
    r = api.delete(f"/api/v1/customers/{METRO}", headers=ADMIN)

    assert r.status_code == 200, r.text
    assert r.json() == {"id": METRO, "name": "Metro Wholesale"}
    with engine.connect() as c:
        tables = c.execute(
            text("""SELECT table_name FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name = 'customer_id'""")
        ).scalars()
        left = {
            t: count(engine, f"SELECT count(*) FROM {t} WHERE customer_id = CAST(:c AS uuid)", c=METRO)
            for t in tables
        }  # noqa: S608  names from the catalogue
    assert all(n == 0 for n in left.values()), left
    assert count(engine, queued, m=mid) == 0
    assert api.get(f"/api/v1/customers/{METRO}", headers=VIEWER).status_code == 404
    assert api.delete(f"/api/v1/customers/{METRO}", headers=ADMIN).status_code == 404


@pytest.mark.parametrize("name", ["Eastern Electricals", "Kumar Electricals", "Vijaya Steel Corporation"])
def test_customers_with_disputes_promises_and_payments_delete_cleanly(api: TestClient, name: str) -> None:
    r = api.delete(f"/api/v1/customers/{uid('customer', name)}", headers=ADMIN)

    assert r.status_code == 200, r.text
    assert name not in [x["name"] for x in api.get("/api/v1/customers", headers=VIEWER).json()["data"]]


def test_a_csv_upload_creates_new_customers_and_adds_to_known_ones(api: TestClient) -> None:
    csv = "\n".join(
        [
            HEADER,
            "Riya Traders,riya@example.com,+919800011111,sme,30,INV-5001,2026-09-01,2026-09-20,125000",
            'Riya Traders,riya@example.com,+919800011111,sme,30,INV-5002,2026-09-05,2026-10-05,"1,25,000.50"',
            "metro wholesale,ignored@example.com,,sme,30,INV-5003,2026-09-10,2026-09-25,50000",
        ]
    )

    r = api.post("/api/v1/customers/import", json={"csv": "﻿" + csv}, headers=COLLECTOR)

    assert r.status_code == 201, r.text
    assert r.json() == {"customers_created": 1, "invoices_added": 3}
    people = {x["name"]: x for x in api.get("/api/v1/customers", headers=VIEWER).json()["data"]}
    assert people["Riya Traders"]["outstanding_paise"] == 12_500_000 + 12_500_050
    numbers = [
        i["number"] for i in api.get(f"/api/v1/customers/{METRO}/invoices", headers=VIEWER).json()["data"]
    ]
    assert "INV-5003" in numbers
    assert (
        people["Metro Wholesale"]["email"] != "ignored@example.com"
    )  # an upload never edits a known customer


@pytest.mark.parametrize(
    ("rows", "fragment"),
    [
        (["Riya Traders,bad-email,,sme,30,INV-5001,2026-09-01,2026-09-20,100"], "row 3"),
        (["Riya Traders,riya@example.com,,sme,30,INV-5001,2026-09-01,2026-09-20,12.345"], "2 decimals"),
        (["Riya Traders,riya@example.com,,sme,30,INV-5001,2026-09-01,2026-09-20,lots"], "not a number"),
        (["Riya Traders,riya@example.com,,sme,30,INV-5001,01/09/2026,2026-09-20,100"], "YYYY-MM-DD"),
        (
            ["Riya Traders,riya@example.com,,sme,30,INV-1021,2026-09-01,2026-09-20,100"],
            "INV-1021 already exists",
        ),
        ([], "no rows"),
    ],
)
def test_a_bad_csv_saves_nothing(api: TestClient, rows: list[str], fragment: str) -> None:
    good = "Asha Stores,asha@example.com,,sme,30,INV-6001,2026-09-01,2026-09-20,100"
    before = len(api.get("/api/v1/customers", headers=VIEWER).json()["data"])

    r = api.post(
        "/api/v1/customers/import",
        json={"csv": "\n".join([HEADER, good, *rows] if rows else [HEADER])},
        headers=COLLECTOR,
    )

    assert r.status_code == 422, r.text
    body = r.json()["error"]
    assert fragment in body["message"] + str(body["details"])
    assert len(api.get("/api/v1/customers", headers=VIEWER).json()["data"]) == before


def test_a_csv_missing_columns_or_too_long_is_refused(api: TestClient) -> None:
    missing = api.post(
        "/api/v1/customers/import", json={"csv": "customer_name,email\nA,a@example.com"}, headers=COLLECTOR
    )
    row = "R,r@example.com,,sme,30,INV-{n},2026-09-01,2026-09-20,100"
    long = "\n".join([HEADER, *(row.format(n=7000 + n) for n in range(501))])
    too_long = api.post("/api/v1/customers/import", json={"csv": long}, headers=COLLECTOR)

    assert missing.status_code == 422 and "Missing columns" in missing.json()["error"]["message"]
    assert too_long.status_code == 422 and "more than 500 rows" in too_long.json()["error"]["message"]


def test_a_csv_over_1_mb_is_refused_even_under_the_character_cap(api: TestClient) -> None:
    rupees = "₹" * 400_000  # 400,000 characters, 1.2 MB in UTF-8

    r = api.post("/api/v1/customers/import", json={"csv": HEADER + "\n" + rupees}, headers=COLLECTOR)

    assert r.status_code == 422
    assert r.json()["error"]["message"] == "The file is over 1 MB."
