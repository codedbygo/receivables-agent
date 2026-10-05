"""Drafts (US-00-005, US-00-006, REQ-046 to REQ-049): the model's prose, the ledger's figures.

{{invoice_table}} and {{total}} are filled here from invoice_balances; the verifier then checks the
final text anyway, so a figure the model typed itself is caught (eng review A7)."""

import json
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.guardrails.verify import Check, InvoiceFact, VerifyContext, verify
from app.services import ledger, memory
from app.services.timeline import Actor, record

Kind = Literal["reminder", "followup", "statement", "dispute_ack"]
NEEDS_TABLE: set[str] = {"reminder", "followup", "statement"}
SUBJECT = {
    "reminder": "Overdue invoices for {name}",
    "followup": "Following up: invoices for {name}",
    "statement": "Statement of account for {name}",
    "dispute_ack": "Your query on {invoices}",
}


class DraftOut(BaseModel):
    message_id: str
    status: Literal["pending_approval", "rejected", "approved"]
    version: int
    invoice_numbers: list[str]
    guardrail_report: list[dict[str, object]]


def _facts(session: Session) -> tuple[dict[str, InvoiceFact], tuple[str, ...]]:
    rows = session.execute(
        text("""SELECT i.number, c.name, i.amount_paise, b.remaining_paise, i.due_date
        FROM invoices i JOIN customers c ON c.id = i.customer_id JOIN invoice_balances b ON b.invoice_id = i.id""")
    ).all()
    facts = {
        r.number: InvoiceFact(r.number, r.name, r.amount_paise, r.remaining_paise, r.due_date) for r in rows
    }
    names: tuple[str, ...] = tuple(
        session.execute(text("SELECT name FROM customers ORDER BY name")).scalars()
    )
    return facts, names


def customer_state(session: Session, customer_id: str) -> tuple[tuple[str, ...], list[Any]]:
    """Open disputed invoice numbers and every promise: the verifier context drafting and editing share."""
    disputed: tuple[str, ...] = tuple(
        session.execute(
            text("""SELECT i.number FROM disputes x JOIN invoices i ON i.id = x.invoice_id
        WHERE x.customer_id = CAST(:c AS uuid) AND x.status <> 'resolved'"""),
            {"c": customer_id},
        ).scalars()
    )
    promises = list(
        session.execute(
            # The day each promise was made counts as a promise date too: a follow-up may say "On 20 Sep 2026
            # you mentioned..." (HACK-003 F3). It is the business date of the promise_logged event.
            text("""SELECT amount_paise, promised_date FROM promises WHERE customer_id = CAST(:c AS uuid)
            UNION ALL SELECT p.amount_paise, t.business_date FROM promises p JOIN timeline_events t
              ON t.ref_id = p.id AND t.kind = 'promise_logged' WHERE p.customer_id = CAST(:c AS uuid)"""),
            {"c": customer_id},
        ).all()
    )
    return disputed, promises


def draft_message(
    session: Session,
    customer_id: str,
    kind: Kind,
    prose: str,
    tone: str,
    channel: str,
    invoice_numbers: list[str] | None = None,
    run_id: str | None = None,
    actor: Actor = "ai",
) -> DraftOut:
    d = today(session)
    customer = ledger.get_customer(session, d, customer_id)
    facts, names = _facts(session)
    disputed, promises = customer_state(session, customer_id)
    if invoice_numbers:
        for n in invoice_numbers:
            if n not in facts:
                raise AppError(ErrorCode.INVOICE_NOT_FOUND, f"{n} does not exist.")
            if facts[n].customer != customer.name:
                raise AppError(ErrorCode.INVOICE_WRONG_CUSTOMER, f"{n} belongs to another customer.")
            if n in disputed and kind != "dispute_ack":
                raise AppError(ErrorCode.INVOICE_DISPUTED, f"{n} is disputed; reminders are paused.")
        cited = list(invoice_numbers)
    else:  # every open invoice not under dispute (REQ-073), oldest due first; a reminder only past-due ones
        open_ = [
            f
            for f in sorted(facts.values(), key=lambda f: (f.due, f.number))
            if f.customer == customer.name and f.remaining_paise > 0 and (kind != "reminder" or f.due < d)
        ]
        cited = [f.number for f in open_ if f.number not in disputed]
        if kind in NEEDS_TABLE and not cited:  # an empty table would verify as a ₹0 reminder
            if open_:
                raise AppError(
                    ErrorCode.INVOICE_DISPUTED, "Every open invoice is disputed; reminders are paused."
                )
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "Nothing is overdue, so there is nothing to remind about."
            )

    body = prose
    if "{{promise_recall}}" in body:  # HACK-003 F3: the customer's own last promise, from the promise row
        line = memory.latest_recall(session, customer_id)
        body = body.replace("{{promise_recall}}", f"{line}\n\n" if line else "")
    if kind in NEEDS_TABLE and ("{{invoice_table}}" in prose and "{{total}}" in prose):
        table = "\n".join(
            f"{n} | {format_inr(facts[n].remaining_paise)} | due {facts[n].due:%d %b %Y}" for n in cited
        )
        total = format_inr(sum(facts[n].remaining_paise for n in cited))
        body = body.replace("{{invoice_table}}", table).replace("{{total}}", total)
    report = verify(
        body,
        VerifyContext(
            customer=customer.name,
            cited=tuple(cited),
            invoices=facts,
            customer_names=names,
            today=d,
            kind=kind,
            promise_amounts=tuple(p.amount_paise for p in promises),
            promise_dates=tuple(p.promised_date for p in promises),
            disputed=disputed,
        ),
    )
    if kind in NEEDS_TABLE and not ("{{invoice_table}}" in prose and "{{total}}" in prose):
        report.checks.insert(
            0, Check("placeholder", "{{invoice_table}} / {{total}}", False, "PLACEHOLDER_MISSING")
        )
    status: Literal["pending_approval", "rejected"] = "pending_approval" if report.ok else "rejected"
    subject = SUBJECT[kind].format(name=customer.name, invoices=", ".join(cited))
    checks = [c.__dict__ for c in report.checks]

    existing = session.execute(
        text("""SELECT id::text, version FROM messages WHERE customer_id = CAST(:c AS uuid)
        AND kind = :k AND status = 'pending_approval' FOR UPDATE"""),
        {"c": customer_id, "k": kind},
    ).first()
    params = {
        "c": customer_id,
        "r": run_id,
        "k": kind,
        "ch": channel,
        "t": tone,
        "st": status,
        "sub": subject,
        "b": body,
        "rep": json.dumps(checks, default=str),
        "reason": None if report.ok else ", ".join(dict.fromkeys(report.codes)),
    }
    if existing and status == "pending_approval":
        mid, version = existing.id, existing.version + 1
        session.execute(
            text("""UPDATE messages SET body = :b, subject = :sub, tone = :t, version = :v,
            verified_version = :v, guardrail_report = CAST(:rep AS jsonb), agent_run_id = CAST(:r AS uuid),
            updated_at = now() WHERE id = CAST(:id AS uuid)"""),
            {**params, "v": version, "id": mid},
        )
        session.execute(
            text("DELETE FROM message_invoices WHERE message_id = CAST(:id AS uuid)"), {"id": mid}
        )
    else:
        version = 1
        mid = session.execute(
            text("""INSERT INTO messages (customer_id, agent_run_id, kind, channel, tone, status,
            subject, body, verified_version, guardrail_report, rejected_reason)
            VALUES (CAST(:c AS uuid), CAST(:r AS uuid), :k, :ch, :t, :st, :sub, :b,
                    CASE WHEN :st = 'pending_approval' THEN 1 END, CAST(:rep AS jsonb), :reason)
            RETURNING id::text"""),
            params,
        ).scalar_one()
    for n in cited:
        session.execute(
            text("""INSERT INTO message_invoices SELECT CAST(:m AS uuid), id FROM invoices
            WHERE number = :n"""),
            {"m": mid, "n": n},
        )
    total_cited = sum(facts[n].remaining_paise for n in cited)
    record(
        session,
        customer_id,
        "reminder_drafted",
        actor,
        f"{tone.capitalize()} {kind}, {len(cited)} invoices",
        amount_paise=total_cited or None,
        ref_type="message",
        ref_id=mid,
    )
    if report.ok:
        record(
            session,
            customer_id,
            "guardrail_passed",
            "system",
            f"{len(report.checks)} of {len(report.checks)} checks match the ledger",
            ref_type="message",
            ref_id=mid,
        )
    else:
        for c in report.checks:
            if not c.ok:
                session.execute(
                    text("""INSERT INTO guardrail_events (check_name, code, customer_id, message_id,
                    agent_run_id, detail) VALUES (:ch, :code, CAST(:c AS uuid), CAST(:m AS uuid), CAST(:r AS uuid),
                    CAST(:d AS jsonb))"""),
                    {
                        "ch": c.check,
                        "code": c.code,
                        "c": customer_id,
                        "m": mid,
                        "r": run_id,
                        "d": json.dumps({"token": c.token, "expected": c.expected}),
                    },
                )
        record(
            session,
            customer_id,
            "guardrail_failed",
            "system",
            f"Draft rejected: {', '.join(dict.fromkeys(report.codes))}",
            ref_type="message",
            ref_id=mid,
        )
    return DraftOut(
        message_id=mid, status=status, version=version, invoice_numbers=cited, guardrail_report=checks
    )
