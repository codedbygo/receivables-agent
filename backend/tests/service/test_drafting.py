"""US-00-005, US-00-006: placeholders filled from the ledger, verified, saved pending or rejected."""

import os
from datetime import date

import pytest
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
PROSE = (
    "Dear ABC Distributors,\n\nOur records show these invoices past their due date:\n\n{{invoice_table}}\n\n"
    "Total outstanding: {{total}}\n\nCould you confirm a date for payment this week?\n\nRegards,\nAccounts team"
)


@pytest.fixture
def reg(engine: Engine):  # type: ignore[no-untyped-def]
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    return build_registry(engine)


def draft(reg, prose: str = PROSE, **kw: object) -> dict[str, object]:  # type: ignore[no-untyped-def]
    args = {"customer_id": ABC, "kind": "reminder", "prose": prose, "tone": "firm", "channel": "email", **kw}
    out: dict[str, object] = reg.invoke("draft_message", args, ToolContext(actor="ai", source="agent"))
    return out


def one(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


# TC-0177 (AC-US-00-005-2), TC-0178 (AC-US-00-005-3)
def test_placeholders_are_filled_from_the_ledger_and_verified(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    out = draft(reg)

    data = out["data"]
    assert data["status"] == "pending_approval"  # type: ignore[index]
    body = str(one(engine, f"SELECT body FROM messages WHERE id = '{data['message_id']}'"))  # type: ignore[index]
    assert "INV-1021 | ₹4,00,000 | due 11 Sep 2026" in body
    assert "INV-1047 | ₹1,50,000 | due 25 Sep 2026" in body
    assert "Total outstanding: ₹7,50,000" in body
    assert "{{" not in body
    assert (
        one(engine, f"SELECT verified_version = version FROM messages WHERE id = '{data['message_id']}'")
        is True
    )  # type: ignore[index]


# TC-0180 (AC-US-00-005-5)
def test_missing_placeholder_is_rejected_and_not_queued(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    out = draft(reg, prose=PROSE.replace("{{invoice_table}}", "INV-1021 is due"))

    assert out["data"]["status"] == "rejected"  # type: ignore[index]
    assert "PLACEHOLDER_MISSING" in [c["code"] for c in out["data"]["guardrail_report"]]  # type: ignore[index]
    assert one(engine, "SELECT count(*) FROM messages WHERE status = 'pending_approval'") == 0


# TC-0179 (AC-US-00-005-4), TC-0186 (AC-US-00-006-6)
def test_model_typed_amount_is_caught(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    out = draft(reg, prose=PROSE.replace("Could you", "Please pay ₹4,50,000 now. Could you"))

    assert out["data"]["status"] == "rejected"  # type: ignore[index]
    assert one(engine, "SELECT count(*) FROM guardrail_events WHERE code = 'INVENTED_AMOUNT'") == 1
    assert (
        one(
            engine,
            f"SELECT count(*) FROM timeline_events WHERE customer_id = '{ABC}' AND kind = 'guardrail_failed'",
        )
        == 1
    )


# TC-0212 (AC-US-00-016-2)
def test_disputed_invoice_is_left_out_of_a_new_reminder(reg) -> None:  # type: ignore[no-untyped-def]
    ctx = ToolContext(actor="ai", source="agent")
    reg.invoke(
        "log_dispute", {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "short supply"}, ctx
    )

    out = draft(reg)

    assert out["data"]["status"] == "pending_approval"  # type: ignore[index]
    assert out["data"]["invoice_numbers"] == ["INV-1021", "INV-1034"]  # type: ignore[index]


def test_second_draft_replaces_the_pending_one(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    first = draft(reg)
    second = draft(reg, prose=PROSE.replace("this week", "by Friday"))

    assert first["data"]["message_id"] == second["data"]["message_id"]  # type: ignore[index]
    assert one(engine, "SELECT version FROM messages") == 2
    assert one(engine, "SELECT count(*) FROM messages") == 1


def test_timeline_records_drafted_and_passed(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    draft(reg)

    kinds = one(
        engine,
        f"SELECT string_agg(kind, ',' ORDER BY occurred_at, kind) FROM timeline_events WHERE customer_id = '{ABC}' AND business_date = DATE '2026-09-30'",
    )
    assert kinds == "guardrail_passed,reminder_drafted"


def test_reminder_with_every_open_invoice_disputed_is_refused(reg) -> None:  # type: ignore[no-untyped-def]
    ctx = ToolContext(actor="ai", source="agent")
    for n in ("INV-1021", "INV-1034", "INV-1047"):
        reg.invoke("log_dispute", {"customer_id": ABC, "invoice_number": n, "reason": "short supply"}, ctx)

    out = draft(reg)

    assert out["ok"] is False
    assert out["error"]["code"] == "INVOICE_DISPUTED"  # type: ignore[index]


def test_reminder_cites_only_invoices_past_due(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    # HACK-001: reminders said "past their due date" while citing invoices due in October and November.
    venk = uid("customer", "Venkateswara Hardware Mart")
    prose = PROSE.replace("ABC Distributors", "Venkateswara Hardware Mart")

    out = draft(reg, prose, customer_id=venk)

    cited = out["data"]["invoice_numbers"]  # type: ignore[index]
    dues = [one(engine, f"SELECT due_date FROM invoices WHERE number = '{n}'") for n in cited]
    assert cited and all(d < date(2026, 9, 30) for d in dues), dict(zip(cited, dues, strict=True))  # type: ignore[operator]
