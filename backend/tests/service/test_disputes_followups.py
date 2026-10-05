"""HACK-003 F7 dispute routing and lifecycle, F5 automatic follow-up, over HTTP against Postgres."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo, uid
from app.tools.registry import build_registry

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


def draft_id(api: TestClient) -> str:
    api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN)
    [d] = api.get(
        "/api/v1/messages", params={"filter[status]": "pending_approval"}, headers=COLLECTOR
    ).json()["data"]
    return str(d["id"])


def reply(api: TestClient, message_id: str, body: str) -> dict[str, object]:
    out: dict[str, object] = api.post(
        "/api/v1/replies", json={"message_id": message_id, "body": body}, headers=COLLECTOR
    ).json()
    return out


def abc_disputes(api: TestClient) -> list[dict[str, object]]:
    data: list[dict[str, object]] = api.get(
        "/api/v1/disputes", params={"filter[customer_id]": ABC}, headers=VIEWER
    ).json()["data"]
    return data


def test_a_quantity_dispute_is_routed_to_operations(api: TestClient) -> None:
    reply(api, draft_id(api), "INV-1047 was billed for 50 units but we received only 40. Please correct it.")
    [d] = [x for x in abc_disputes(api) if x["invoice_number"] == "INV-1047"]

    assert (d["category"], d["assigned_team"], d["status"]) == ("wrong_quantity", "operations", "assigned")
    kinds = [e["kind"] for e in api.get(f"/api/v1/customers/{ABC}/timeline", headers=VIEWER).json()["data"]]
    assert "dispute_assigned" in kinds


def test_lifecycle_moves_forward_and_only_a_person_resolves(api: TestClient) -> None:
    reply(api, draft_id(api), "INV-1047 was billed for 50 units but we received only 40. Please correct it.")
    [d] = [x for x in abc_disputes(api) if x["invoice_number"] == "INV-1047"]
    url = f"/api/v1/disputes/{d['id']}"

    assert api.post(f"{url}/transition", json={"to": "investigating"}, headers=VIEWER).status_code == 403
    moved = api.post(
        f"{url}/transition", json={"to": "investigating", "note": "Checking GRN"}, headers=COLLECTOR
    )
    assert moved.json()["status"] == "investigating"
    back = api.post(f"{url}/transition", json={"to": "assigned"}, headers=COLLECTOR)
    assert back.status_code == 422
    # still active: the disputed invoice stays out of every figure and every reminder
    assert any(
        f["code"] == "OPEN_DISPUTES"
        for f in api.get(f"/api/v1/customers/{ABC}/priority", headers=VIEWER).json()["factors"]
    )
    assert api.post(f"{url}/resolve", json={"note": ""}, headers=COLLECTOR).status_code == 422
    done = api.post(
        f"{url}/resolve", json={"note": "Credit note CN-12 issued for 10 units"}, headers=COLLECTOR
    )
    assert done.json()["status"] == "resolved"


def test_no_tool_can_resolve_or_move_a_dispute(engine: Engine) -> None:
    names = set(build_registry(engine).tools)
    assert not {n for n in names if "resolve" in n or "transition" in n}


def promise_then_advance(api: TestClient, mode: str, days: int = 6) -> None:
    if mode != "manual":
        api.patch("/api/v1/admin/settings", json={"autonomy_mode": mode}, headers=ADMIN)
    reply(api, draft_id(api), "We can pay ₹3 lakh on October 5 and the remaining amount later.")
    api.post("/api/v1/admin/clock/advance", json={"days": days}, headers=ADMIN)


def followups(api: TestClient, status: str = "open") -> list[dict[str, object]]:
    data: list[dict[str, object]] = api.get(
        "/api/v1/follow-ups", params={"filter[customer_id]": ABC, "filter[status]": status}, headers=VIEWER
    ).json()["data"]
    return data


def test_a_missed_promise_in_manual_mode_creates_a_task_and_no_draft(api: TestClient) -> None:
    before = len(followups(api))
    promise_then_advance(api, "manual")
    tasks = followups(api)

    new = [t for t in tasks if t["promised_date"] == "2026-10-05"]
    assert len(tasks) == before + 1 and len(new) == 1
    t = new[0]
    assert (t["promised_paise"], t["received_paise"], t["promise_status"]) == (30_000_000, 0, "missed")
    assert str(t["recommended_action"]).startswith("Contact the customer today")
    assert t["message_id"] is None


def test_assisted_mode_drafts_a_follow_up_that_recalls_the_promise_and_waits(api: TestClient) -> None:
    promise_then_advance(api, "assisted")
    [t] = [t for t in followups(api) if t["promised_date"] == "2026-10-05"]
    msg = api.get(f"/api/v1/messages/{t['message_id']}", headers=COLLECTOR).json()

    assert msg["kind"] == "followup" and msg["status"] == "pending_approval"
    assert "On 30 Sep 2026, you mentioned that ₹3,00,000 would be paid on 05 Oct 2026." in msg["body"]
    assert msg["verified"] is True


def test_trusted_mode_never_auto_sends_a_follow_up(api: TestClient) -> None:
    api.patch("/api/v1/admin/settings", json={"feature_trusted_mode": True}, headers=ADMIN)
    promise_then_advance(api, "trusted")
    [t] = [t for t in followups(api) if t["promised_date"] == "2026-10-05"]

    assert (
        api.get(f"/api/v1/messages/{t['message_id']}", headers=COLLECTOR).json()["status"]
        == "pending_approval"
    )


def test_a_fulfilled_promise_creates_no_task_and_evaluation_is_idempotent(api: TestClient) -> None:
    before = len(followups(api))
    reply(api, draft_id(api), "We can pay ₹3 lakh on October 5 and the remaining amount later.")
    api.post("/api/v1/admin/clock/advance", json={"days": 5}, headers=ADMIN)
    api.post(
        "/api/v1/admin/simulate/bank-credit",
        json={"customer_id": ABC, "amount_paise": 30_000_000, "reference": "NEFT ABC Distributors UTR 4411"},
        headers=ADMIN,
    )
    api.post("/api/v1/admin/clock/advance", json={"days": 2}, headers=ADMIN)

    assert len(followups(api)) == before


def test_closing_a_follow_up_needs_a_collector_and_a_note(api: TestClient) -> None:
    promise_then_advance(api, "manual")
    [t] = [t for t in followups(api) if t["promised_date"] == "2026-10-05"]
    url = f"/api/v1/follow-ups/{t['id']}/close"

    assert api.post(url, json={"status": "done", "note": "Called"}, headers=VIEWER).status_code == 403
    assert api.post(url, json={"status": "done", "note": ""}, headers=COLLECTOR).status_code == 422
    assert (
        api.post(url, json={"status": "done", "note": "Called; new date 12 Oct"}, headers=COLLECTOR).json()[
            "status"
        ]
        == "done"
    )
