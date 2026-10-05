"""Customer memory (HACK-003 F3): what happened with this customer, in order, from rows only.

Two views. agent_view() is what the model and MCP clients may read: dates, kinds, ledger amounts and code-written
summaries, never a reply body, dispute text or an internal note (customer text is untrusted, T-18). full() adds the
collector notes for signed-in people. Memory never changes a figure: amounts are ledger columns, and the recall
sentence is rendered by code from the promise row and checked by the verifier like every draft line."""

from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.services.timeline import record

SUMMARY = {  # code-written text per timeline kind; the customer's own words never enter memory
    "reminder_drafted": "Reminder drafted",
    "approved": "Message approved",
    "rejected": "Draft rejected by a collector",
    "sent": "Message sent",
    "send_failed": "Message could not be sent",
    "reply_received": "Customer replied",
    "promise_logged": "Customer promised a payment",
    "promise_fulfilled": "Promise kept",
    "promise_partially_fulfilled": "Promise partly kept",
    "promise_missed": "Promise missed",
    "payment_received": "Payment received",
    "payment_matched": "Payment allocated to an invoice",
    "dispute_opened": "Customer raised a dispute",
    "dispute_assigned": "Dispute routed to a team",
    "dispute_investigating": "Dispute under investigation",
    "dispute_resolved": "Dispute resolved",
    "escalation_created": "Handed to a person",
    "followup_created": "Follow-up task created",
    "followup_closed": "Follow-up closed",
    "call_requested": "Call requested",
    "call_completed": "Call completed",
    "call_failed": "Call did not connect",
}
SOURCE = {
    "sent": "message",
    "reply_received": "reply",
    "send_failed": "message",
    "payment_received": "payment",
    "payment_matched": "payment",
    "call_requested": "call",
    "call_completed": "call",
    "call_failed": "call",
}


class MemoryItem(BaseModel):
    on: date
    kind: str
    source: str
    summary: str
    amount_paise: int | None
    channel: str | None


class Note(BaseModel):
    id: str
    body: str
    author: str | None
    created_at: datetime


class AgentMemory(BaseModel):
    customer_id: str
    items: list[MemoryItem]
    promise_recall: str | None


class Memory(AgentMemory):
    notes: list[Note]


def _source(kind: str) -> str:
    return SOURCE.get(kind) or kind.split("_")[0]


def agent_view(session: Session, customer_id: str, limit: int = 40) -> AgentMemory:
    if not session.execute(
        text("SELECT 1 FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id}
    ).scalar():
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    rows = session.execute(
        text("""SELECT t.business_date, t.kind, t.amount_paise,
        (SELECT m.channel FROM messages m WHERE t.ref_type = 'message' AND m.id = t.ref_id) AS channel
        FROM timeline_events t WHERE t.customer_id = CAST(:c AS uuid) AND t.kind = ANY(CAST(:k AS text[]))
        ORDER BY t.occurred_at DESC LIMIT :l"""),
        {"c": customer_id, "k": list(SUMMARY), "l": limit},
    ).all()
    items = [
        MemoryItem(
            on=r.business_date,
            kind=r.kind,
            source=_source(r.kind),
            summary=SUMMARY[r.kind],
            amount_paise=r.amount_paise,
            channel=r.channel,
        )
        for r in reversed(rows)
    ]
    return AgentMemory(
        customer_id=customer_id, items=items, promise_recall=latest_recall(session, customer_id)
    )


def latest_recall(session: Session, customer_id: str) -> str | None:
    """The recall sentence for the most recent missed or partly kept promise, or None."""
    pid = session.execute(
        text("""SELECT id::text FROM promises WHERE customer_id = CAST(:c AS uuid)
        AND status IN ('missed', 'partially_fulfilled') ORDER BY promised_date DESC, created_at DESC LIMIT 1"""),
        {"c": customer_id},
    ).scalar()
    return recall(session, str(pid)) if pid else None


def recall(session: Session, promise_id: str) -> str:
    """The sentence that reminds the customer of their own promise, built from the promise row (F3).
    The day it was made is the business date of its promise_logged event."""
    p = session.execute(
        text("""SELECT p.amount_paise, p.promised_date, p.status, (SELECT t.business_date FROM timeline_events t
        WHERE t.ref_id = p.id AND t.kind = 'promise_logged' ORDER BY t.occurred_at LIMIT 1) AS made_on
        FROM promises p WHERE p.id = CAST(:p AS uuid)"""),
        {"p": promise_id},
    ).one()
    said = f"you mentioned that {format_inr(p.amount_paise)} would be paid on {p.promised_date:%d %b %Y}."
    opening = f"On {p.made_on:%d %b %Y}, {said}" if p.made_on else said[0].upper() + said[1:]
    tail = (
        "Only part of it has reached us so far."
        if p.status == "partially_fulfilled"
        else "We have not received the payment yet."
    )
    return f"{opening} {tail}"


def full(session: Session, customer_id: str) -> Memory:
    base = agent_view(session, customer_id)
    notes = [
        Note(id=r.id, body=r.body, author=r.author, created_at=r.created_at)
        for r in session.execute(
            text("""SELECT n.id::text, n.body, u.display_name AS author, n.created_at FROM customer_notes n
            LEFT JOIN users u ON u.id = n.author_id WHERE n.customer_id = CAST(:c AS uuid)
            ORDER BY n.created_at DESC LIMIT 50"""),
            {"c": customer_id},
        )
    ]
    return Memory(**base.model_dump(), notes=notes)


def add_note(session: Session, customer_id: str, body: str, user_id: str) -> Note:
    body = body.strip()
    if not body or len(body) > 2000:
        raise AppError(ErrorCode.VALIDATION_ERROR, "A note is 1 to 2,000 characters.")
    agent_view(session, customer_id, limit=1)  # 404 for an unknown customer
    r = session.execute(
        text("""INSERT INTO customer_notes (customer_id, author_id, body) VALUES (CAST(:c AS uuid),
        CAST(:u AS uuid), :b) RETURNING id::text, created_at"""),
        {"c": customer_id, "u": user_id, "b": body},
    ).one()
    record(  # the note itself stays internal; the timeline says only that one was added
        session,
        customer_id,
        "note_added",
        "human",
        "Internal note added",
        ref_type="note",
        ref_id=r.id,
        actor_user_id=user_id,
    )
    author = session.execute(
        text("SELECT display_name FROM users WHERE id = CAST(:u AS uuid)"), {"u": user_id}
    ).scalar()
    return Note(id=r.id, body=body, author=author, created_at=r.created_at)
