"""US-03-002: tool registry behaviour (schemas, typed errors, no raw SQL, call bound) and the five
tools whose services exist in P0 step 6. draft_message and send_message join in steps 7 and 9."""

import os
from datetime import date

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services import approval
from app.services.demo import reset_demo, uid
from app.tools.registry import Registry, ToolContext, build_registry

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
METRO = uid("customer", "Metro Wholesale")


@pytest.fixture
def reg(engine: Engine):  # type: ignore[no-untyped-def]
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    return build_registry(engine)


def ctx(**kw: object) -> ToolContext:
    return ToolContext(actor="ai", source="agent", **kw)  # type: ignore[arg-type]


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_list_overdue_returns_the_ranked_customers(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("list_overdue", {"limit": 15}, ctx())

    assert out["ok"] is True
    assert len(out["data"]["customers"]) == 15
    abc = next(c for c in out["data"]["customers"] if c["customer_id"] == ABC)
    assert (abc["band"], abc["overdue_paise"]) == ("HIGH", 75_000_000)


# TC-0247 (AC-US-03-002-2)
def test_bad_input_type_is_a_validation_error_and_nothing_runs(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("list_overdue", {"limit": "ten"}, ctx())

    assert out == {"ok": False, "error": out["error"]}
    assert out["error"]["code"] == "VALIDATION_ERROR"


# TC-0249 (AC-US-03-002-4)
def test_raw_sql_field_is_refused_and_logged(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("get_customer_history", {"customer_id": ABC, "sql": "DROP TABLE invoices"}, ctx())

    assert out["error"]["code"] == "VALIDATION_ERROR"
    assert scalar(engine, "SELECT count(*) FROM guardrail_events WHERE code = 'DIRECT_DB_ATTEMPT'") == 1
    assert scalar(engine, "SELECT count(*) FROM invoices") == 300


# TC-0249 (AC-US-03-002-4)
def test_injection_text_in_an_id_is_just_a_bad_uuid(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("get_customer_history", {"customer_id": "'; DROP TABLE invoices; --"}, ctx())

    assert out["error"]["code"] == "VALIDATION_ERROR"


def test_history_has_no_reply_bodies(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("get_customer_history", {"customer_id": ABC}, ctx())

    data = out["data"]
    assert [i["number"] for i in data["invoices"] if i["status"] == "unpaid"] == [
        "INV-1021",
        "INV-1034",
        "INV-1047",
    ]
    assert data["promises"][0]["status"] == "missed"
    assert "We will pay" not in str(data)  # T-18: summaries only


def test_fifth_call_is_not_executed(reg) -> None:  # type: ignore[no-untyped-def]
    c = ctx(max_calls=4)
    for _ in range(4):
        assert reg.invoke("list_overdue", {}, c)["ok"] is True

    out = reg.invoke("list_overdue", {}, c)

    assert out["error"]["code"] == "TOOL_LIMIT"
    assert c.calls == 4


def test_tool_outside_the_allow_list_is_refused_and_counted(reg) -> None:  # type: ignore[no-untyped-def]
    c = ctx(allowed=frozenset({"list_overdue"}), max_calls=4)

    out = reg.invoke("log_dispute", {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "x"}, c)

    assert out["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert c.calls == 1


# TC-0210 (AC-US-00-014-1), TC-0211 (AC-US-00-014-2)
def test_log_promise_links_oldest_invoice_and_writes_timeline(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke(
        "log_promise", {"customer_id": ABC, "amount_paise": 30_000_000, "promised_date": "2026-10-05"}, ctx()
    )

    assert out["ok"] and out["data"]["status"] == "pending"
    assert out["data"]["invoice_numbers"] == ["INV-1021"]
    assert (
        scalar(
            engine,
            f"SELECT count(*) FROM timeline_events WHERE customer_id = '{ABC}' AND kind = 'promise_logged' AND business_date = DATE '2026-09-30'",
        )
        == 1
    )


def test_log_promise_rejects_another_customers_invoice(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke(
        "log_promise",
        {
            "customer_id": ABC,
            "amount_paise": 100,
            "promised_date": "2026-10-05",
            "invoice_numbers": ["INV-1301"],
        },
        ctx(),
    )

    assert out["error"]["code"] == "INVOICE_WRONG_CUSTOMER"


def test_log_dispute_marks_invoice_and_refuses_a_second_open_one(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    args = {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "quantity mismatch"}

    first = reg.invoke("log_dispute", args, ctx())
    second = reg.invoke("log_dispute", args, ctx())

    assert first["ok"] and first["data"]["status"] == "open"
    assert scalar(engine, "SELECT status FROM invoices WHERE number = 'INV-1047'") == "disputed"
    assert second["error"]["code"] == "DISPUTE_EXISTS"


def test_log_dispute_on_unknown_invoice(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("log_dispute", {"customer_id": ABC, "invoice_number": "INV-9999", "reason": "x"}, ctx())

    assert out["error"]["code"] == "INVOICE_NOT_FOUND"


def test_escalate_is_idempotent_per_source(reg, engine: Engine) -> None:  # type: ignore[no-untyped-def]
    d = reg.invoke(
        "log_dispute", {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "short"}, ctx()
    )
    args = {
        "customer_id": ABC,
        "kind": "dispute",
        "reason": "INV-1047 disputed",
        "dispute_id": d["data"]["id"],
    }

    a = reg.invoke("escalate", args, ctx())
    b = reg.invoke("escalate", args, ctx())

    assert a["data"]["id"] == b["data"]["id"]
    assert scalar(engine, f"SELECT count(*) FROM escalations WHERE dispute_id = '{d['data']['id']}'") == 1


def test_every_tool_output_matches_its_schema(reg) -> None:  # type: ignore[no-untyped-def]
    out = reg.invoke("get_customer_history", {"customer_id": METRO}, ctx())

    reg.tools["get_customer_history"].output.model_validate(out["data"])
    assert date.fromisoformat(out["data"]["today"]) == date(2026, 9, 30)


ABC_PROSE = (
    "Dear ABC Distributors,\n\nThese invoices are past their due date:\n\n{{invoice_table}}\n\n"
    "Total outstanding: {{total}}\n\nCould you confirm a payment date?\n\nRegards,\nAccounts team"
)


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_customer", {"customer_id": ABC}),
        ("get_invoice", {"invoice_number": "INV-1034"}),
        ("check_promise_status", {"customer_id": ABC}),
        ("create_followup", {"customer_id": ABC, "prose": ABC_PROSE}),
    ],
)
# TC-0251 (AC-US-03-003-1)
def test_additional_tool_answers_in_its_schema(reg: Registry, tool: str, args: dict[str, object]) -> None:
    # US-03-003: the additional MCP tools validate input and answer in their declared output schema
    out = reg.invoke(tool, args, ctx())

    assert "data" in out, out
    reg.tools[tool].output.model_validate(out["data"])


# Audit finding 7: a reply, dispute or payment named by id must belong to the customer the tool acts for.
def error_code(out: dict[str, object]) -> object:
    error = out.get("error")
    return error.get("code") if isinstance(error, dict) else None


def test_log_promise_refuses_another_customers_reply(reg: Registry, engine: Engine) -> None:
    other_reply = scalar(engine, f"SELECT id::text FROM replies WHERE customer_id <> '{ABC}' LIMIT 1")
    args = {
        "customer_id": ABC,
        "amount_paise": 30_000_000,
        "promised_date": "2026-10-05",
        "reply_id": other_reply,
    }
    out = reg.invoke("log_promise", args, ctx())
    assert error_code(out) == "MESSAGE_CUSTOMER_MISMATCH"
    assert scalar(engine, f"SELECT count(*) FROM promises WHERE reply_id = '{other_reply}'") == 0


def test_escalate_refuses_another_customers_reply(reg: Registry, engine: Engine) -> None:
    other_reply = scalar(engine, f"SELECT id::text FROM replies WHERE customer_id <> '{ABC}' LIMIT 1")
    args = {"customer_id": ABC, "kind": "dispute", "reason": "check", "reply_id": other_reply}
    out = reg.invoke("escalate", args, ctx())
    assert error_code(out) == "MESSAGE_CUSTOMER_MISMATCH"


def test_log_dispute_refuses_another_customers_reply(reg: Registry, engine: Engine) -> None:
    other_reply = scalar(engine, f"SELECT id::text FROM replies WHERE customer_id <> '{ABC}' LIMIT 1")
    args = {
        "customer_id": ABC,
        "invoice_number": "INV-1047",
        "reason": "wrong quantity",
        "reply_id": other_reply,
    }
    assert error_code(reg.invoke("log_dispute", args, ctx())) == "MESSAGE_CUSTOMER_MISMATCH"


# TC-0248 (AC-US-03-002-3): every core tool, called with valid input, answers in its declared output schema.
def test_every_core_tool_output_validates_against_its_schema(reg: Registry, engine: Engine) -> None:
    c = ctx()
    draft = reg.invoke(
        "draft_message",
        {
            "customer_id": ABC,
            "kind": "reminder",
            "tone": "firm",
            "prose": "Dear ABC Distributors,\n\nThese invoices are past due:\n\n{{invoice_table}}\n\n"
            "Total outstanding: {{total}}\n\nCould you confirm a payment date?\n\nRegards,\nAccounts team",
        },
        c,
    )
    data = draft["data"]
    assert isinstance(data, dict)
    with Session(bind=engine) as s, s.begin():
        approval.approve(s, str(data["message_id"]), None, None)
    calls = {
        "list_overdue": {"limit": 15},
        "get_customer_history": {"customer_id": ABC},
        "send_message": {"message_id": data["message_id"]},
        "log_promise": {"customer_id": ABC, "amount_paise": 30_000_000, "promised_date": "2026-10-05"},
        "log_dispute": {"customer_id": ABC, "invoice_number": "INV-1047", "reason": "wrong quantity"},
        "escalate": {"customer_id": ABC, "kind": "dispute", "reason": "customer disputes INV-1047"},
    }
    outputs = {"draft_message": draft} | {name: reg.invoke(name, args, ctx()) for name, args in calls.items()}

    for name, out in outputs.items():
        assert out["ok"], (name, out.get("error"))
        reg.tools[name].output.model_validate(out["data"])
    assert len(outputs) == 7
