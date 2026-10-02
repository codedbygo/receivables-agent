"""P2 behind flags (brief 4.19): Trusted mode, simulated WhatsApp, Prepare Call, the simulated payment link
(US-01-016, US-00-024, US-00-025, US-03-004). Each flag off refuses with FEATURE_DISABLED (AC-US-01-016-4)."""

import os
import smtplib
import time
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.channels.email import WhatsAppChannel
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services import approval
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
METRO = uid("customer", "Metro Wholesale")
ADMIN = {"X-Demo-Role": "admin"}
COLLECTOR = {"X-Demo-Role": "collector"}
PROSE = (
    "Dear {name},\n\nA gentle reminder that these invoices are now past due:\n\n{{{{invoice_table}}}}\n\n"
    "Total outstanding: {{{{total}}}}\n\nPlease let us know when we can expect payment.\n\nRegards,\nAccounts team"
)


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    settings = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, settings)
    with TestClient(create_app(settings)) as c:
        yield c


def flags(api: TestClient, **values: object) -> None:
    r = api.patch("/api/v1/admin/settings", json=values, headers=ADMIN)
    assert r.status_code == 200, r.text


def draft(engine: Engine, customer: str, name: str, tone: str) -> dict[str, object]:
    out = build_registry(engine).invoke(
        "draft_message",
        {"customer_id": customer, "kind": "reminder", "prose": PROSE.format(name=name), "tone": tone},
        ToolContext(actor="ai", source="agent"),
    )
    assert out["ok"], out
    data: dict[str, object] = out["data"]
    return data


def status(engine: Engine, message_id: object) -> str:
    with engine.connect() as c:
        return str(c.execute(text(f"SELECT status FROM messages WHERE id = '{message_id}'")).scalar())


# TC-0278 (AC-US-01-016-3)
def test_trusted_mode_auto_approves_only_an_allow_listed_gentle_reminder(
    api: TestClient, engine: Engine
) -> None:
    flags(api, feature_trusted_mode=True, autonomy_mode="trusted")

    small = draft(engine, METRO, "Metro Wholesale", "gentle")
    firm = draft(engine, METRO, "Metro Wholesale", "firm")
    big = draft(engine, ABC, "ABC Distributors", "gentle")

    assert status(engine, small["message_id"]) == "approved"
    assert status(engine, firm["message_id"]) == "pending_approval"
    assert status(engine, big["message_id"]) == "pending_approval"


def test_manual_mode_never_auto_approves(api: TestClient, engine: Engine) -> None:
    flags(api, feature_trusted_mode=True)

    small = draft(engine, METRO, "Metro Wholesale", "gentle")

    assert status(engine, small["message_id"]) == "pending_approval"


# TC-0279 (AC-US-01-016-4)
def test_trusted_mode_needs_its_flag(api: TestClient) -> None:
    r = api.patch("/api/v1/admin/settings", json={"autonomy_mode": "trusted"}, headers=ADMIN)

    assert r.json()["error"]["code"] == "FEATURE_DISABLED"


# TC-0272 (AC-US-00-024-1), TC-0273 (AC-US-00-024-2), TC-0279 (AC-US-01-016-4)
def test_whatsapp_reminder_goes_through_the_simulated_adapter(api: TestClient, engine: Engine) -> None:
    m = draft(engine, METRO, "Metro Wholesale", "gentle")
    url = f"/api/v1/messages/{m['message_id']}"
    msg = api.get(url, headers=COLLECTOR).json()
    body = {"subject": msg["subject"], "body": msg["body"], "channel": "whatsapp"}

    off = api.patch(url, json=body, headers={**COLLECTOR, "If-Match": str(msg["version"])})
    flags(api, feature_whatsapp=True)
    on = api.patch(url, json=body, headers={**COLLECTOR, "If-Match": str(msg["version"])}).json()
    api.post(f"{url}/approve", headers={**COLLECTOR, "If-Match": str(on["version"])})
    approval.deliver(engine, str(m["message_id"]), {"whatsapp": WhatsAppChannel()})

    assert off.json()["error"]["code"] == "FEATURE_DISABLED"
    assert on["channel"] == "whatsapp"
    assert api.get(url, headers=COLLECTOR).json()["status"] == "sent"


# TC-0274 (AC-US-00-025-1), TC-0279 (AC-US-01-016-4)
def test_call_prep_is_a_sheet_from_the_ledger(api: TestClient) -> None:
    off = api.get(f"/api/v1/customers/{ABC}/call-prep", headers=COLLECTOR)
    flags(api, feature_voice=True)

    sheet = api.get(f"/api/v1/customers/{ABC}/call-prep", headers=COLLECTOR).json()

    assert off.json()["error"]["code"] == "FEATURE_DISABLED"
    assert [i["number"] for i in sheet["invoices"]] == ["INV-1021", "INV-1034", "INV-1047"]
    assert any(p["status"] == "missed" for p in sheet["promises"])
    assert "₹7,50,000" in sheet["summary"]
    assert sheet["verified"] is True and sheet["talking_points"]


# TC-0276 (AC-US-03-004-1), TC-0277 (AC-US-03-004-2), TC-0279 (AC-US-01-016-4)
def test_payment_link_pays_the_invoice_through_the_ledger(api: TestClient) -> None:
    link = "/api/v1/invoices/INV-1034/pay-link"
    off = api.post(link, headers=COLLECTOR)
    flags(api, feature_payment_link=True)
    token = api.post(link, headers=COLLECTOR).json()["token"]

    page = api.get(f"/api/v1/pay/{token}").json()
    paid = api.post(f"/api/v1/pay/{token}").json()
    again = api.post(f"/api/v1/pay/{token}")
    forged = api.get(f"/api/v1/pay/{token[:-2]}xx")

    assert off.json()["error"]["code"] == "FEATURE_DISABLED"
    assert (page["invoice_number"], page["amount_paise"], page["simulated"]) == ("INV-1034", 20_000_000, True)
    assert paid["match_status"] == "matched"
    assert [a["invoice_number"] for a in paid["allocations"]] == ["INV-1034"]
    assert again.json()["error"]["code"] == "VALIDATION_ERROR"
    assert forged.status_code == 404
    customer = api.get(f"/api/v1/customers/{ABC}", headers=COLLECTOR).json()
    assert customer["outstanding_paise"] == 55_000_000


def test_payment_link_expires(api: TestClient, engine: Engine) -> None:
    # Security review 2026-10-01 (T-41): a forwarded link must not work forever.
    from sqlalchemy.orm import Session

    from app.services import paylink

    flags(api, feature_payment_link=True)
    with Session(bind=engine) as s, s.begin():
        old = paylink.create(s, "k", "INV-1034", now=1_000.0).token
        fresh = paylink.create(s, "k", "INV-1034", now=time.time()).token
        with pytest.raises(AppError) as e:
            paylink.read(s, "k", old)
        assert e.value.code == ErrorCode.NOT_FOUND
        assert paylink.read(s, "k", fresh).invoice_number == "INV-1034"


# TC-0275 (AC-US-00-025-2): the voice feature prepares a call sheet and places no call.
def test_voice_makes_no_outbound_request(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("outbound request from the voice path")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(smtplib.SMTP, "connect", refuse)
    flags(api, feature_voice=True)

    sheet = api.get(f"/api/v1/customers/{ABC}/call-prep", headers=COLLECTOR)

    assert sheet.status_code == 200 and sheet.json()["talking_points"]
