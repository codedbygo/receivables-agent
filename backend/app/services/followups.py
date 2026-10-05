"""Automatic follow-up (HACK-003 F5). When a promise is missed or only partly kept, evaluate_promises calls
on_broken_promise in the same transaction:

    Manual   -> a follow-up task with a recommended action
    Assisted -> the task, plus a follow-up draft waiting in Approvals
    Trusted  -> the same as Assisted: a follow-up is never auto-approved (policy trusted_mode_allow refuses
                customers with a missed promise, and this path does not call trusted_approve at all)

Every figure in the draft comes from the promise row and the ledger; the verifier checks it like any draft."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.services import drafting
from app.services.runtime import autonomy_mode
from app.services.timeline import record

FOLLOWUP = (
    "Dear {name},\n\n{{{{promise_recall}}}}Could you please share an updated payment date?\n\n"
    "These invoices remain open:\n\n{{{{invoice_table}}}}\n\nTotal outstanding: {{{{total}}}}\n\n"
    "Regards,\nAccounts team"
)
ACTION = {
    "missed_promise": "Contact the customer today: the promised payment has not arrived.",
    "partial_promise": "Contact the customer today: only part of the promised payment arrived.",
}


class FollowUp(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    promise_id: str
    kind: str
    status: str
    due_on: date
    recommended_action: str
    promised_paise: int
    promised_date: date
    received_paise: int
    promise_status: str
    message_id: str | None
    created_at: datetime


def on_broken_promise(
    session: Session, customer_id: str, promise_id: str, kind: Literal["missed_promise", "partial_promise"]
) -> str | None:
    """Create the task (once per promise) and, outside Manual mode, a follow-up draft. Returns the task id,
    or None when the promise already has one."""
    d = today(session)
    tid = session.execute(
        text("""INSERT INTO follow_up_tasks (customer_id, promise_id, kind, due_on, recommended_action)
        VALUES (CAST(:c AS uuid), CAST(:p AS uuid), :k, :d, :a)
        ON CONFLICT (promise_id) DO NOTHING RETURNING id::text"""),
        {"c": customer_id, "p": promise_id, "k": kind, "d": d, "a": ACTION[kind]},
    ).scalar()
    if tid is None:
        return None
    mode = autonomy_mode(session)
    record(
        session,
        customer_id,
        "followup_created",
        "system",
        f"Follow-up task: {ACTION[kind]} (mode {mode})",
        ref_type="follow_up",
        ref_id=tid,
    )
    if mode == "manual":
        return str(tid)
    name: str = session.execute(
        text("SELECT name FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id}
    ).scalar_one()
    try:
        draft = drafting.draft_message(
            session,
            customer_id,
            "followup",
            FOLLOWUP.format(name=name),
            "firm",
            "email",
            actor="system",
        )
    except AppError:  # nothing left to chase (all paid or all disputed): the task alone tells the collector
        return str(tid)
    session.execute(
        text("UPDATE follow_up_tasks SET message_id = CAST(:m AS uuid) WHERE id = CAST(:t AS uuid)"),
        {"m": draft.message_id, "t": tid},
    )
    return str(tid)


def list_followups(
    session: Session, status: str | None, customer_id: str | None, limit: int = 100
) -> list[FollowUp]:
    rows = session.execute(
        text("""SELECT f.id::text, f.customer_id::text, c.name AS customer_name, f.promise_id::text, f.kind,
        f.status, f.due_on, f.recommended_action, p.amount_paise AS promised_paise, p.promised_date,
        p.status AS promise_status, f.message_id::text, f.created_at,
        (SELECT COALESCE(SUM(pay.amount_paise), 0) FROM payments pay WHERE pay.customer_id = p.customer_id
          AND pay.match_status = 'matched' AND pay.received_on <= p.promised_date
          AND pay.created_at >= p.created_at) AS received_paise
        FROM follow_up_tasks f JOIN promises p ON p.id = f.promise_id JOIN customers c ON c.id = f.customer_id
        WHERE (CAST(:s AS text) IS NULL OR f.status = :s)
          AND (CAST(:c AS uuid) IS NULL OR f.customer_id = CAST(:c AS uuid))
        ORDER BY f.due_on DESC, f.created_at DESC LIMIT :l"""),
        {"s": status, "c": customer_id, "l": limit},
    ).mappings()
    return [FollowUp(**{**r, "received_paise": int(r["received_paise"])}) for r in rows]


def close(
    session: Session, task_id: str, status: Literal["done", "cancelled"], note: str, user_id: str
) -> FollowUp:
    if not note.strip():
        raise AppError(ErrorCode.REASON_REQUIRED, "Add a note so the timeline explains the outcome.")
    row = session.execute(
        text("SELECT customer_id::text, status FROM follow_up_tasks WHERE id = CAST(:t AS uuid) FOR UPDATE"),
        {"t": task_id},
    ).first()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Follow-up not found.")
    if row.status == "open":
        session.execute(
            text("""UPDATE follow_up_tasks SET status = :s, closed_by = CAST(:u AS uuid), closed_at = now(),
            close_note = :n WHERE id = CAST(:t AS uuid)"""),
            {"s": status, "u": user_id, "n": note.strip(), "t": task_id},
        )
        record(
            session,
            row.customer_id,
            "followup_closed",
            "human",
            f"Follow-up {status}: {note.strip()[:80]}",
            ref_type="follow_up",
            ref_id=task_id,
            actor_user_id=user_id,
        )
    return next(f for f in list_followups(session, None, row.customer_id) if f.id == task_id)
