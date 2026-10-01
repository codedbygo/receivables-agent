"""Prepare Call (US-00-025, REQ-061, REQ-090): a call sheet built from the ledger, never a call. The talking
points are written by code from ledger figures and still pass the same guardrails as a draft."""

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.guardrails.verify import Check, VerifyContext, verify
from app.services import ledger, overview
from app.services.drafting import _facts


class CallPrep(BaseModel):
    customer: ledger.Customer
    summary: str
    invoices: list[ledger.Invoice]
    promises: list[overview.PromiseRow]
    talking_points: list[str]
    verified: bool
    checks: list[dict[str, object]]


def prepare(session: Session, customer_id: str) -> CallPrep:
    if not session.execute(text("SELECT feature_voice FROM settings WHERE id = 1")).scalar():
        raise AppError(ErrorCode.FEATURE_DISABLED, "Prepare Call is switched off.")
    d = today(session)
    c = ledger.get_customer(session, d, customer_id)
    invoices = [i for i in ledger.customer_invoices(session, d, customer_id) if i.remaining_paise > 0]
    promises = overview.list_promises(session, None, customer_id, None, 10)
    disputed = [i for i in invoices if i.status == "disputed"]
    chase = [i for i in invoices if i.status != "disputed"]
    oldest = max((i.days_overdue for i in chase), default=0)

    summary = (
        f"{c.name} owes {format_inr(c.outstanding_paise)} across {len(invoices)} open invoices"
        + (f"; the oldest is {oldest} days overdue" if oldest else "")
        + (f"; priority {c.band}" if c.band else "")
        + "."
    )
    points = ["Confirm the invoices due for payment:"]
    points += [f"{i.number} for {format_inr(i.remaining_paise)}, due {i.due_date:%d %b %Y}" for i in chase]
    points += [
        f"The promise of {format_inr(p.amount_paise)} for {p.promised_date:%d %b %Y} was missed; ask what changed."
        for p in promises
        if p.status == "missed"
    ]
    points += [
        f"{i.number} is under dispute; do not ask for it, a collector is resolving it." for i in disputed
    ]
    points.append("Ask for a firm payment date this week and note it as a promise.")

    facts, names = _facts(session)
    report = verify(
        "\n".join([summary, *points]),
        VerifyContext(
            customer=c.name,
            cited=tuple(i.number for i in invoices),
            invoices=facts,
            customer_names=names,
            today=d,
            kind="reminder",
            promise_amounts=tuple(p.amount_paise for p in promises),
            promise_dates=tuple(p.promised_date for p in promises),
        ),
    )
    return CallPrep(
        customer=c,
        summary=summary,
        invoices=invoices,
        promises=promises,
        talking_points=points,
        verified=report.ok,
        checks=[_check(x) for x in report.checks],
    )


def _check(x: Check) -> dict[str, object]:
    return {"check": x.check, "token": x.token, "ok": x.ok, "code": x.code, "expected": x.expected}
