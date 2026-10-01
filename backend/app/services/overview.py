"""Read models for the console: dashboard, timeline, next action, runs (US-00-003, US-00-004, US-00-008,
US-00-022). Every figure is SQL over the ledger; nothing here writes."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.services.priority import priorities


class TimelineEvent(BaseModel):
    id: str
    occurred_at: datetime
    business_date: date
    kind: str
    actor: str
    actor_name: str | None
    amount_paise: int | None
    summary: str
    ref_type: str | None
    ref_id: str | None


class Step(BaseModel):
    seq: int
    role: str
    tool_name: str
    arguments_redacted: dict[str, Any]
    result_summary: str
    error_code: str | None


class Run(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    run_date: date
    trigger: str
    status: str
    outcome: str | None
    tool_call_count: int
    action: str | None
    channel: str | None
    tone: str | None
    reason: str | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[Step]


def timeline(session: Session, customer_id: str, limit: int = 200) -> list[TimelineEvent]:
    rows = session.execute(
        text("""SELECT t.id::text, t.occurred_at, t.business_date, t.kind, t.actor,
        u.display_name AS actor_name, t.amount_paise, t.summary, t.ref_type, t.ref_id::text
        FROM timeline_events t LEFT JOIN users u ON u.id = t.actor_user_id
        WHERE t.customer_id = CAST(:c AS uuid) ORDER BY t.occurred_at DESC, t.kind LIMIT :l"""),
        {"c": customer_id, "l": limit},
    ).mappings()
    return [TimelineEvent(**r) for r in rows]


def next_action(session: Session, customer_id: str, today: date) -> str:
    """Rules, not the model (AC-US-00-004-2, -3)."""
    q = session.execute(
        text("""SELECT
        EXISTS (SELECT 1 FROM disputes WHERE customer_id = CAST(:c AS uuid) AND status = 'open') AS dispute,
        EXISTS (SELECT 1 FROM messages WHERE customer_id = CAST(:c AS uuid) AND status = 'pending_approval') AS draft,
        EXISTS (SELECT 1 FROM messages WHERE customer_id = CAST(:c AS uuid) AND status = 'approved') AS approved,
        (SELECT min(promised_date) FROM promises WHERE customer_id = CAST(:c AS uuid) AND status = 'pending') AS pending,
        EXISTS (SELECT 1 FROM promises WHERE customer_id = CAST(:c AS uuid) AND status = 'missed'
                AND resolved_at > COALESCE((SELECT max(sent_at) FROM messages WHERE customer_id = CAST(:c AS uuid)),
                                           'epoch')) AS missed,
        (SELECT COALESCE(SUM(b.remaining_paise), 0) FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id
          WHERE i.customer_id = CAST(:c AS uuid) AND i.due_date < :d AND i.status <> 'disputed') AS overdue"""),
        {"c": customer_id, "d": today},
    ).one()
    if q.dispute:
        return "Resolve dispute"
    if q.draft:
        return "Review the draft in Approvals"
    if q.approved:
        return "Approved reminder is sending"
    if q.pending:
        return f"Wait for the promise due {q.pending:%d %b %Y}"
    if q.missed:
        return "Send follow-up on missed promise"
    if q.overdue:
        return "Send reminder"
    return "No action needed"


def runs(
    session: Session, customer_id: str | None = None, run_id: str | None = None, limit: int = 20
) -> list[Run]:
    rows = (
        session.execute(
            text("""SELECT r.id::text, r.customer_id::text, c.name AS customer_name, r.run_date,
        r.trigger, r.status, r.outcome, r.tool_call_count, r.action, r.channel, r.tone, r.reason, r.started_at,
        r.finished_at FROM agent_runs r JOIN customers c ON c.id = r.customer_id
        WHERE (CAST(:c AS uuid) IS NULL OR r.customer_id = CAST(:c AS uuid))
          AND (CAST(:r AS uuid) IS NULL OR r.id = CAST(:r AS uuid))
        ORDER BY r.started_at DESC LIMIT :l"""),
            {"c": customer_id, "r": run_id, "l": limit},
        )
        .mappings()
        .all()
    )
    out = []
    for r in rows:
        steps = [
            Step(**s)
            for s in session.execute(
                text("""SELECT seq, role, tool_name, arguments_redacted,
            result_summary, error_code FROM agent_steps WHERE agent_run_id = CAST(:r AS uuid) ORDER BY seq"""),
                {"r": r["id"]},
            ).mappings()
        ]
        out.append(Run(**r, steps=steps))
    if run_id and not out:
        raise AppError(ErrorCode.NOT_FOUND, "Run not found.")
    return out


def dashboard(session: Session, today: date) -> dict[str, Any]:
    t = session.execute(
        text("""SELECT
        COALESCE(SUM(b.remaining_paise), 0) AS outstanding,
        COALESCE(SUM(b.remaining_paise) FILTER (WHERE i.due_date < :d), 0) AS overdue,
        COUNT(DISTINCT i.customer_id) FILTER (WHERE i.due_date < :d AND b.remaining_paise > 0) AS customers_overdue,
        COALESCE(SUM(b.remaining_paise) FILTER (WHERE :d - i.due_date BETWEEN 0 AND 30), 0) AS a0,
        COALESCE(SUM(b.remaining_paise) FILTER (WHERE :d - i.due_date BETWEEN 31 AND 60), 0) AS a31,
        COALESCE(SUM(b.remaining_paise) FILTER (WHERE :d - i.due_date BETWEEN 61 AND 90), 0) AS a61,
        COALESCE(SUM(b.remaining_paise) FILTER (WHERE :d - i.due_date > 90), 0) AS a90
        FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id WHERE b.remaining_paise > 0"""),
        {"d": today},
    ).one()
    counts = session.execute(
        text("""SELECT
        (SELECT count(*) FROM promises WHERE status = 'pending' AND promised_date = :d) AS todays,
        (SELECT count(*) FROM promises WHERE status = 'missed') AS missed,
        (SELECT count(*) FROM disputes WHERE status = 'open') AS disputes,
        (SELECT count(*) FROM messages WHERE status = 'pending_approval') AS pending,
        (SELECT count(*) FROM escalations WHERE status = 'open') AS escalations"""),
        {"d": today},
    ).one()
    ranked = priorities(session, today)
    high = [
        {
            "customer_id": cid,
            "customer_name": name,
            "score": p.score,
            "band": p.band,
            "reasons": [r.model_dump() for r in p.reasons],
        }
        for cid, name, p in ranked
        if p.band == "HIGH"
    ]

    def listing(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in session.execute(text(sql), {"d": today}).mappings()]

    return {
        "today": today,
        "total_outstanding_paise": t.outstanding,
        "total_overdue_paise": t.overdue,
        "customers_overdue": t.customers_overdue,
        "todays_promises": counts.todays,
        "missed_promises": counts.missed,
        "open_disputes": counts.disputes,
        "pending_approvals": counts.pending,
        "high_risk_customers": len(high),
        "open_escalations": counts.escalations,
        "ageing": {
            "d0_30_paise": t.a0,
            "d31_60_paise": t.a31,
            "d61_90_paise": t.a61,
            "d90_plus_paise": t.a90,
        },
        "attention": {
            "high_priority": high[:7],
            "missed_promises": listing("""SELECT p.id::text, p.customer_id::text, c.name AS customer_name, p.amount_paise,
                p.promised_date, p.status FROM promises p JOIN customers c ON c.id = p.customer_id
                WHERE p.status = 'missed' ORDER BY p.promised_date DESC LIMIT 10"""),
            "disputes": listing("""SELECT d.id::text, d.customer_id::text, c.name AS customer_name, i.number AS invoice_number,
                d.reason, d.status FROM disputes d JOIN customers c ON c.id = d.customer_id
                JOIN invoices i ON i.id = d.invoice_id WHERE d.status = 'open' ORDER BY d.created_at DESC LIMIT 10"""),
            "approved_ready": listing("""SELECT m.id::text, m.customer_id::text, c.name AS customer_name, m.subject
                FROM messages m JOIN customers c ON c.id = m.customer_id WHERE m.status = 'approved' LIMIT 10"""),
            "needs_verification": listing("""SELECT id::text, amount_paise, reference, received_on FROM payments
                WHERE match_status = 'needs_verification' ORDER BY created_at DESC LIMIT 10"""),
            "todays_promises": listing("""SELECT p.id::text, p.customer_id::text, c.name AS customer_name, p.amount_paise,
                p.promised_date, p.status FROM promises p JOIN customers c ON c.id = p.customer_id
                WHERE p.promised_date = :d ORDER BY c.name"""),
            "escalations": listing("""SELECT e.id::text, e.customer_id::text, c.name AS customer_name, e.kind, e.reason,
                e.created_at FROM escalations e JOIN customers c ON c.id = e.customer_id WHERE e.status = 'open'
                ORDER BY e.created_at DESC LIMIT 10"""),
        },
    }


class PromiseRow(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    amount_paise: int
    promised_date: date
    status: str
    invoice_ids: list[str]


class DisputeRow(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    invoice_id: str
    invoice_number: str
    reason: str
    status: str
    resolution_note: str | None


class EscalationRow(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    kind: str
    reason: str
    status: str
    created_at: datetime


class PaymentRow(BaseModel):
    id: str
    customer_id: str | None
    customer_name: str | None
    amount_paise: int
    received_on: date
    reference: str | None
    source: str
    match_status: str


class ReplyRow(BaseModel):
    id: str
    customer_id: str
    message_id: str | None
    body: str
    classification: str | None
    amount_paise: int | None
    stated_date: date | None
    invoice_refs: list[str]
    confidence: float | None
    recommended_action: str | None
    needs_review: bool
    agent_run_id: str | None


class GuardrailEventRow(BaseModel):
    id: str
    check_name: str
    code: str
    customer_id: str | None
    message_id: str | None
    detail: dict[str, Any]
    created_at: datetime


def list_promises(
    session: Session, status: str | None, customer_id: str | None, due: date | None, limit: int = 100
) -> list[PromiseRow]:
    rows = session.execute(
        text("""SELECT p.id::text, p.customer_id::text, c.name AS customer_name, p.amount_paise,
        p.promised_date, p.status, COALESCE((SELECT array_agg(pi.invoice_id::text) FROM promise_invoices pi
        WHERE pi.promise_id = p.id), '{}') AS invoice_ids
        FROM promises p JOIN customers c ON c.id = p.customer_id
        WHERE (CAST(:s AS text) IS NULL OR p.status = :s)
          AND (CAST(:c AS uuid) IS NULL OR p.customer_id = CAST(:c AS uuid))
          AND (CAST(:d AS date) IS NULL OR p.promised_date = :d)
        ORDER BY p.promised_date DESC, p.id LIMIT :l"""),
        {"s": status, "c": customer_id, "d": due, "l": limit},
    ).mappings()
    return [PromiseRow(**{**r, "invoice_ids": list(r["invoice_ids"])}) for r in rows]


def list_disputes(
    session: Session, status: str | None, customer_id: str | None, limit: int = 100
) -> list[DisputeRow]:
    rows = session.execute(
        text("""SELECT d.id::text, d.customer_id::text, c.name AS customer_name,
        d.invoice_id::text, i.number AS invoice_number, d.reason, d.status, d.resolution_note
        FROM disputes d JOIN customers c ON c.id = d.customer_id JOIN invoices i ON i.id = d.invoice_id
        WHERE (CAST(:s AS text) IS NULL OR d.status = :s) AND (CAST(:c AS uuid) IS NULL OR d.customer_id = CAST(:c AS uuid))
        ORDER BY d.created_at DESC, d.id LIMIT :l"""),
        {"s": status, "c": customer_id, "l": limit},
    ).mappings()
    return [DisputeRow(**r) for r in rows]


def list_escalations(
    session: Session, status: str | None, customer_id: str | None, limit: int = 100
) -> list[EscalationRow]:
    rows = session.execute(
        text("""SELECT e.id::text, e.customer_id::text, c.name AS customer_name, e.kind, e.reason,
        e.status, e.created_at FROM escalations e JOIN customers c ON c.id = e.customer_id
        WHERE (CAST(:s AS text) IS NULL OR e.status = :s) AND (CAST(:c AS uuid) IS NULL OR e.customer_id = CAST(:c AS uuid))
        ORDER BY e.created_at DESC, e.id LIMIT :l"""),
        {"s": status, "c": customer_id, "l": limit},
    ).mappings()
    return [EscalationRow(**r) for r in rows]


def list_payments(
    session: Session, match_status: str | None, customer_id: str | None, limit: int = 100
) -> list[PaymentRow]:
    rows = session.execute(
        text("""SELECT p.id::text, p.customer_id::text, c.name AS customer_name, p.amount_paise,
        p.received_on, p.reference, p.source, p.match_status FROM payments p LEFT JOIN customers c ON c.id = p.customer_id
        WHERE (CAST(:s AS text) IS NULL OR p.match_status = :s)
          AND (CAST(:c AS uuid) IS NULL OR p.customer_id = CAST(:c AS uuid))
        ORDER BY p.received_on DESC, p.created_at DESC LIMIT :l"""),
        {"s": match_status, "c": customer_id, "l": limit},
    ).mappings()
    return [PaymentRow(**r) for r in rows]


def get_reply(session: Session, reply_id: str) -> ReplyRow:
    r = (
        session.execute(
            text("""SELECT r.id::text, r.customer_id::text, r.message_id::text, r.body, r.classification,
        r.amount_paise, r.stated_date, r.invoice_refs, r.confidence::float AS confidence, r.recommended_action,
        r.needs_review, (SELECT a.id::text FROM agent_runs a WHERE a.customer_id = r.customer_id AND a.trigger = 'reply'
          AND a.started_at >= r.received_at ORDER BY a.started_at LIMIT 1) AS agent_run_id
        FROM replies r WHERE r.id = CAST(:r AS uuid)"""),
            {"r": reply_id},
        )
        .mappings()
        .first()
    )
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Reply not found.")
    return ReplyRow(**{**r, "invoice_refs": list(r["invoice_refs"])})


def guardrail_events(session: Session, code: str | None, limit: int = 100) -> list[GuardrailEventRow]:
    rows = session.execute(
        text("""SELECT id::text, check_name, code, customer_id::text, message_id::text, detail,
        created_at FROM guardrail_events WHERE (CAST(:c AS text) IS NULL OR code = :c)
        ORDER BY created_at DESC, id LIMIT :l"""),
        {"c": code, "l": limit},
    ).mappings()
    return [GuardrailEventRow(**r) for r in rows]
