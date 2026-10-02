"""Promises, disputes, escalations and customer history (US-00-014, US-00-016, US-03-001)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.services import ledger
from app.services.timeline import Actor, record

EscalationKind = Literal[
    "dispute", "low_confidence", "injection_suspected", "claim_not_found", "payment_needs_verification"
]


class PromiseOut(BaseModel):
    id: str
    customer_id: str
    amount_paise: int
    promised_date: date
    status: str
    invoice_numbers: list[str]


class DisputeOut(BaseModel):
    id: str
    customer_id: str
    invoice_number: str
    reason: str
    status: str


class EscalationOut(BaseModel):
    id: str
    customer_id: str
    kind: str
    reason: str
    status: str


class MessageSummary(BaseModel):
    subject: str
    status: str
    sent_at: str | None


class ReplySummary(BaseModel):
    classification: str | None
    received_on: date


class History(BaseModel):
    today: date
    customer: ledger.Customer
    invoices: list[ledger.Invoice]
    promises: list[PromiseOut]
    disputes: list[DisputeOut]
    last_messages: list[MessageSummary]
    reply_summaries: list[ReplySummary]


def _invoices_of(session: Session, customer_id: str, numbers: list[str]) -> list[tuple[str, str]]:
    """(id, number) for each number; refuses unknown numbers and other customers' invoices."""
    rows = session.execute(
        text("SELECT id::text, number, customer_id::text FROM invoices WHERE number = ANY(:n)"),
        {"n": numbers},
    ).all()
    found = {r.number: r for r in rows}
    for n in numbers:
        if n not in found:
            raise AppError(ErrorCode.INVOICE_NOT_FOUND, f"{n} does not exist.")
        if found[n].customer_id != customer_id:
            raise AppError(ErrorCode.INVOICE_WRONG_CUSTOMER, f"{n} belongs to another customer.")
    return [(found[n].id, n) for n in numbers]


OWNED = {
    "reply_id": "SELECT 1 FROM replies WHERE id = CAST(:i AS uuid) AND customer_id = CAST(:c AS uuid)",
    "dispute_id": "SELECT 1 FROM disputes WHERE id = CAST(:i AS uuid) AND customer_id = CAST(:c AS uuid)",
    # an unmatched bank payment has no customer yet and may be escalated from any customer's context
    "payment_id": """SELECT 1 FROM payments WHERE id = CAST(:i AS uuid)
        AND (customer_id IS NULL OR customer_id = CAST(:c AS uuid))""",
}


def _owned(session: Session, customer_id: str, **refs: str | None) -> None:
    """A reply, dispute or payment named by id must be this customer's (security audit finding 7)."""
    for key, ref in refs.items():
        if (
            ref is not None
            and session.execute(text(OWNED[key]), {"i": ref, "c": customer_id}).scalar() is None
        ):
            raise AppError(ErrorCode.MESSAGE_CUSTOMER_MISMATCH, "That record belongs to another customer.")


def log_promise(
    session: Session,
    customer_id: str,
    amount_paise: int,
    promised_date: date,
    invoice_numbers: list[str] | None = None,
    reply_id: str | None = None,
    actor: Actor = "ai",
) -> PromiseOut:
    ledger.get_customer(session, today(session), customer_id)
    _owned(session, customer_id, reply_id=reply_id)
    if reply_id:
        existing = session.execute(
            text("SELECT id::text FROM promises WHERE reply_id = CAST(:r AS uuid) AND status = 'pending'"),
            {"r": reply_id},
        ).scalar()
        if existing:
            return _promise(session, existing)
    if invoice_numbers:
        linked = _invoices_of(session, customer_id, invoice_numbers)
    else:  # oldest open first, up to the amount (Q-012)
        rows = session.execute(
            text("""SELECT i.id::text, i.number, b.remaining_paise FROM invoices i
            JOIN invoice_balances b ON b.invoice_id = i.id
            WHERE i.customer_id = CAST(:c AS uuid) AND b.remaining_paise > 0 AND i.status <> 'disputed'
            ORDER BY i.due_date, i.number"""),
            {"c": customer_id},
        ).all()
        linked, covered = [], 0
        for r in rows:
            if covered >= amount_paise:
                break
            linked.append((r.id, r.number))
            covered += r.remaining_paise
    pid: str = session.execute(
        text("""INSERT INTO promises (customer_id, reply_id, amount_paise, promised_date)
        VALUES (CAST(:c AS uuid), CAST(:r AS uuid), :a, :d) RETURNING id::text"""),
        {"c": customer_id, "r": reply_id, "a": amount_paise, "d": promised_date},
    ).scalar_one()
    for inv_id, _ in linked:
        session.execute(
            text("INSERT INTO promise_invoices VALUES (CAST(:p AS uuid), CAST(:i AS uuid))"),
            {"p": pid, "i": inv_id},
        )
    record(
        session,
        customer_id,
        "promise_logged",
        actor,
        f"Promise {format_inr(amount_paise)} on {promised_date:%d %b %Y}",
        amount_paise=amount_paise,
        ref_type="promise",
        ref_id=pid,
    )
    return _promise(session, pid)


def _promise(session: Session, pid: str) -> PromiseOut:
    r = session.execute(
        text("""SELECT p.id::text, p.customer_id::text, p.amount_paise, p.promised_date, p.status,
        COALESCE(array_agg(i.number ORDER BY i.due_date) FILTER (WHERE i.number IS NOT NULL), '{}') AS numbers
        FROM promises p LEFT JOIN promise_invoices pi ON pi.promise_id = p.id LEFT JOIN invoices i ON i.id = pi.invoice_id
        WHERE p.id = CAST(:p AS uuid) GROUP BY p.id"""),
        {"p": pid},
    ).one()
    return PromiseOut(
        id=r.id,
        customer_id=r.customer_id,
        amount_paise=r.amount_paise,
        promised_date=r.promised_date,
        status=r.status,
        invoice_numbers=list(r.numbers),
    )


def log_dispute(
    session: Session,
    customer_id: str,
    invoice_number: str,
    reason: str,
    reply_id: str | None = None,
    actor: Actor = "ai",
) -> DisputeOut:
    [(inv_id, _)] = _invoices_of(session, customer_id, [invoice_number])
    _owned(session, customer_id, reply_id=reply_id)
    if session.execute(
        text("SELECT 1 FROM disputes WHERE invoice_id = CAST(:i AS uuid) AND status = 'open'"), {"i": inv_id}
    ).scalar():
        raise AppError(ErrorCode.DISPUTE_EXISTS, f"{invoice_number} already has an open dispute.")
    did: str = session.execute(
        text("""INSERT INTO disputes (customer_id, invoice_id, reply_id, reason)
        VALUES (CAST(:c AS uuid), CAST(:i AS uuid), CAST(:r AS uuid), :reason) RETURNING id::text"""),
        {"c": customer_id, "i": inv_id, "r": reply_id, "reason": reason},
    ).scalar_one()
    session.execute(
        text("UPDATE invoices SET status = 'disputed', updated_at = now() WHERE id = CAST(:i AS uuid)"),
        {"i": inv_id},
    )
    record(
        session,
        customer_id,
        "dispute_opened",
        "customer" if actor == "ai" else actor,
        f"Dispute on {invoice_number}: {reason[:80]}",
        ref_type="dispute",
        ref_id=did,
    )
    return DisputeOut(
        id=did, customer_id=customer_id, invoice_number=invoice_number, reason=reason, status="open"
    )


def escalate(
    session: Session,
    customer_id: str,
    kind: EscalationKind,
    reason: str,
    dispute_id: str | None = None,
    reply_id: str | None = None,
    payment_id: str | None = None,
) -> EscalationOut:
    ledger.get_customer(session, today(session), customer_id)
    _owned(session, customer_id, dispute_id=dispute_id, reply_id=reply_id, payment_id=payment_id)
    existing = session.execute(
        text("""SELECT id::text FROM escalations WHERE customer_id = CAST(:c AS uuid)
        AND kind = :k AND status = 'open' AND dispute_id IS NOT DISTINCT FROM CAST(:d AS uuid)
        AND reply_id IS NOT DISTINCT FROM CAST(:r AS uuid) AND payment_id IS NOT DISTINCT FROM CAST(:p AS uuid)"""),
        {"c": customer_id, "k": kind, "d": dispute_id, "r": reply_id, "p": payment_id},
    ).scalar()
    eid = (
        existing
        or session.execute(
            text("""INSERT INTO escalations (customer_id, kind, reason, dispute_id,
        reply_id, payment_id) VALUES (CAST(:c AS uuid), :k, :reason, CAST(:d AS uuid), CAST(:r AS uuid),
        CAST(:p AS uuid)) RETURNING id::text"""),
            {"c": customer_id, "k": kind, "reason": reason, "d": dispute_id, "r": reply_id, "p": payment_id},
        ).scalar_one()
    )
    if not existing:
        record(
            session, customer_id, "escalation_created", "system", reason, ref_type="escalation", ref_id=eid
        )
    return EscalationOut(id=eid, customer_id=customer_id, kind=kind, reason=reason, status="open")


def history(session: Session, customer_id: str) -> History:
    """What the agent may know about a customer. Summaries only: no reply bodies (T-18)."""
    d = today(session)
    customer = ledger.get_customer(session, d, customer_id)
    p = {"c": customer_id}
    promise_ids: list[str] = list(
        session.execute(
            text(
                "SELECT id::text FROM promises WHERE customer_id = CAST(:c AS uuid) ORDER BY promised_date DESC LIMIT 10"
            ),
            p,
        ).scalars()
    )
    promises = [_promise(session, pid) for pid in promise_ids]
    disputes = [
        DisputeOut(
            id=r.id,
            customer_id=customer_id,
            invoice_number=r.number,
            reason=r.reason.split(":")[0],
            status=r.status,
        )  # category only: the rest is customer text, untrusted for the model and MCP clients
        for r in session.execute(
            text("""SELECT d.id::text, i.number, d.reason, d.status FROM disputes d
                    JOIN invoices i ON i.id = d.invoice_id WHERE d.customer_id = CAST(:c AS uuid)
                    ORDER BY d.created_at DESC LIMIT 10"""),
            p,
        )
    ]
    messages = [
        MessageSummary(
            subject=r.subject, status=r.status, sent_at=r.sent_at.isoformat() if r.sent_at else None
        )
        for r in session.execute(
            text("""SELECT subject, status, sent_at FROM messages
                    WHERE customer_id = CAST(:c AS uuid) ORDER BY created_at DESC LIMIT 5"""),
            p,
        )
    ]
    replies = [
        ReplySummary(classification=r.classification, received_on=r.received_at.date())
        for r in session.execute(
            text("""SELECT classification, received_at FROM replies
                   WHERE customer_id = CAST(:c AS uuid) ORDER BY received_at DESC LIMIT 5"""),
            p,
        )
    ]
    return History(
        today=d,
        customer=customer,
        invoices=ledger.customer_invoices(session, d, customer_id),
        promises=promises,
        disputes=disputes,
        last_messages=messages,
        reply_summaries=replies,
    )


def resolve_dispute(session: Session, dispute_id: str, note: str, user_id: str | None) -> DisputeOut:
    """A collector closes a dispute; the invoice status returns to what its balance says (AC-US-00-016-5)."""
    if not note.strip():
        raise AppError(ErrorCode.REASON_REQUIRED, "Add a note so the timeline explains the outcome.")
    r = session.execute(
        text("""SELECT d.id::text, d.customer_id::text, d.invoice_id::text, i.number, d.reason, d.status
        FROM disputes d JOIN invoices i ON i.id = d.invoice_id WHERE d.id = CAST(:d AS uuid) FOR UPDATE OF d"""),
        {"d": dispute_id},
    ).first()
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Dispute not found.")
    if r.status == "resolved":
        return DisputeOut(
            id=r.id, customer_id=r.customer_id, invoice_number=r.number, reason=r.reason, status="resolved"
        )
    session.execute(
        text("""UPDATE disputes SET status = 'resolved', resolution_note = :n, resolved_at = now()
        WHERE id = CAST(:d AS uuid)"""),
        {"n": note.strip(), "d": dispute_id},
    )
    session.execute(
        text("""UPDATE invoices i SET status = CASE WHEN b.remaining_paise = 0 THEN 'paid'
        WHEN b.paid_paise > 0 THEN 'partially_paid' ELSE 'unpaid' END, updated_at = now()
        FROM invoice_balances b WHERE b.invoice_id = i.id AND i.id = CAST(:i AS uuid)"""),
        {"i": r.invoice_id},
    )
    session.execute(
        text("""UPDATE escalations SET status = 'resolved', resolved_by = CAST(:u AS uuid), resolved_at = now()
        WHERE dispute_id = CAST(:d AS uuid) AND status = 'open'"""),
        {"u": user_id, "d": dispute_id},
    )
    record(
        session,
        r.customer_id,
        "dispute_resolved",
        "human",
        f"Dispute on {r.number} resolved. Reminders resume.",
        ref_type="dispute",
        ref_id=r.id,
        actor_user_id=user_id,
    )
    return DisputeOut(
        id=r.id, customer_id=r.customer_id, invoice_number=r.number, reason=r.reason, status="resolved"
    )


def resolve_escalation(session: Session, escalation_id: str, note: str, user_id: str | None) -> EscalationOut:
    r = session.execute(
        text("""SELECT id::text, customer_id::text, kind, reason, status FROM escalations
        WHERE id = CAST(:e AS uuid) FOR UPDATE"""),
        {"e": escalation_id},
    ).first()
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Escalation not found.")
    if r.status == "open":
        session.execute(
            text("""UPDATE escalations SET status = 'resolved', resolved_by = CAST(:u AS uuid),
            resolved_at = now() WHERE id = CAST(:e AS uuid)"""),
            {"u": user_id, "e": escalation_id},
        )
        record(
            session,
            r.customer_id,
            "escalation_resolved",
            "human",
            f"Escalation closed: {note.strip()[:80]}",
            ref_type="escalation",
            ref_id=r.id,
            actor_user_id=user_id,
        )
    return EscalationOut(id=r.id, customer_id=r.customer_id, kind=r.kind, reason=r.reason, status="resolved")
