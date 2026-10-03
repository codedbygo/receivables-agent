"""Approval queue and the send gate (US-00-009, US-00-010, US-00-011, US-01-002, REQ-043, REQ-058, REQ-099).

Every send path (API resend, worker, MCP send_message) goes through send_gate() (tenet 4)."""

import json
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.channels.email import ChannelError, MessageChannel, Outbound
from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.guardrails.verify import VerifyContext, policy, verify
from app.services.drafting import _facts, customer_state
from app.services.priority import priorities
from app.services.timeline import record
from app.worker.jobs import Defer, enqueue

MAX_SEND_ATTEMPTS = 5


class Message(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    agent_run_id: str | None
    kind: str
    channel: str
    tone: str
    status: Literal["draft", "pending_approval", "approved", "rejected", "sent", "failed"]
    subject: str
    body: str
    version: int
    verified: bool
    guardrail_report: list[dict[str, Any]]
    invoice_numbers: list[str]
    rejected_reason: str | None
    sent_at: str | None
    last_error: str | None
    created_at: str


_SELECT = """SELECT m.id::text, m.customer_id::text, c.name AS customer_name, m.agent_run_id::text, m.kind, m.channel,
  m.tone, m.status, m.subject, m.body, m.version, (m.verified_version = m.version) AS verified,
  COALESCE(m.guardrail_report, '[]'::jsonb) AS guardrail_report,
  COALESCE((SELECT array_agg(i.number ORDER BY i.due_date) FROM message_invoices mi JOIN invoices i ON i.id = mi.invoice_id
            WHERE mi.message_id = m.id), '{}') AS invoice_numbers,
  m.rejected_reason, m.sent_at::text, m.last_error, m.created_at::text
FROM messages m JOIN customers c ON c.id = m.customer_id"""


def get_message(session: Session, message_id: str) -> Message:
    r = (
        session.execute(text(_SELECT + " WHERE m.id = CAST(:m AS uuid)"), {"m": message_id})
        .mappings()
        .first()
    )
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Message not found.")
    return Message(**{**r, "verified": bool(r["verified"]), "invoice_numbers": list(r["invoice_numbers"])})


def list_messages(
    session: Session, status: str | None, customer_id: str | None, limit: int = 100
) -> list[Message]:
    rows = session.execute(
        text(
            _SELECT
            + """ WHERE (CAST(:s AS text) IS NULL OR m.status = :s)
        AND (CAST(:c AS uuid) IS NULL OR m.customer_id = CAST(:c AS uuid)) ORDER BY m.created_at DESC LIMIT :l"""
        ),
        {"s": status, "c": customer_id, "l": limit},
    ).mappings()
    return [
        Message(**{**r, "verified": bool(r["verified"]), "invoice_numbers": list(r["invoice_numbers"])})
        for r in rows
    ]


def _lock(session: Session, message_id: str, if_match: int | None) -> Any:
    row = session.execute(
        text("""SELECT id::text, customer_id::text, status, version, verified_version, body
        FROM messages WHERE id = CAST(:m AS uuid) FOR UPDATE"""),
        {"m": message_id},
    ).first()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Message not found.")
    if if_match is not None and if_match != row.version:
        raise AppError(ErrorCode.STALE_DRAFT, "This draft changed in another tab. Reload the draft.")
    return row


def approve(session: Session, message_id: str, if_match: int | None, user_id: str | None) -> Message:
    row = _lock(session, message_id, if_match)
    if row.status in ("approved", "sent"):
        return get_message(session, message_id)  # idempotent double click (CEO review D1)
    if row.status != "pending_approval":
        raise AppError(ErrorCode.NOT_APPROVED, f"A {row.status} message cannot be approved.")
    if row.verified_version != row.version:
        raise AppError(ErrorCode.NOT_VERIFIED, "The current text has not passed the guardrails.")
    session.execute(
        text("""UPDATE messages SET status = 'approved', approved_by = CAST(:u AS uuid), approved_at = now(),
        updated_at = now() WHERE id = CAST(:m AS uuid)"""),
        {"u": user_id, "m": message_id},
    )
    record(
        session,
        row.customer_id,
        "approved",
        "human",
        "Reminder approved",
        ref_type="message",
        ref_id=message_id,
        actor_user_id=user_id,
    )
    enqueue(session.connection(), "send_message", message_id, {"message_id": message_id})
    return get_message(session, message_id)


def get_message_now(factory: sessionmaker[Session], message_id: str) -> Message:
    """The message as committed, after any inline send."""
    with factory() as session:
        return get_message(session, message_id)


def reject(session: Session, message_id: str, reason: str, user_id: str | None) -> Message:
    if not reason.strip():
        raise AppError(ErrorCode.REASON_REQUIRED, "Add a reason so the next run can learn from it.")
    row = _lock(session, message_id, None)
    if row.status != "pending_approval":
        raise AppError(ErrorCode.NOT_APPROVED, f"A {row.status} message cannot be rejected.")
    session.execute(
        text("""UPDATE messages SET status = 'rejected', rejected_reason = :r, updated_at = now()
        WHERE id = CAST(:m AS uuid)"""),
        {"r": reason.strip(), "m": message_id},
    )
    record(
        session,
        row.customer_id,
        "rejected",
        "human",
        f"Draft rejected: {reason.strip()[:80]}",
        ref_type="message",
        ref_id=message_id,
        actor_user_id=user_id,
    )
    return get_message(session, message_id)


def edit(
    session: Session,
    message_id: str,
    subject: str,
    body: str,
    if_match: int | None,
    user_id: str | None,
    channel: Literal["email", "whatsapp"] | None = None,
) -> Message:
    """Edited text is verified again before it is saved (REQ-057); a failing edit changes nothing.
    A collector may move a draft to simulated WhatsApp while that flag is on (US-00-024)."""
    row = _lock(session, message_id, if_match)
    if (
        channel == "whatsapp"
        and not session.execute(text("SELECT feature_whatsapp FROM settings WHERE id = 1")).scalar()
    ):
        raise AppError(ErrorCode.FEATURE_DISABLED, "WhatsApp is switched off.")
    if row.status != "pending_approval":
        raise AppError(ErrorCode.NOT_APPROVED, f"A {row.status} message cannot be edited.")
    msg = get_message(session, message_id)
    facts, names = _facts(session)
    disputed, promises = customer_state(session, msg.customer_id)
    report = verify(  # the subject goes out too, so it is checked with the body
        f"{subject}\n{body}",
        VerifyContext(
            customer=msg.customer_name,
            cited=tuple(msg.invoice_numbers),
            invoices=facts,
            customer_names=names,
            today=today(session),
            kind=msg.kind,
            promise_amounts=tuple(p.amount_paise for p in promises),
            promise_dates=tuple(p.promised_date for p in promises),
            disputed=disputed,
        ),
    )
    if not report.ok:
        bad = [c for c in report.checks if not c.ok]
        first = bad[0]
        hint = f" (ledger: {first.expected})" if first.expected else ""
        raise AppError(
            ErrorCode(first.code or "VALIDATION_ERROR"),
            f"{first.token} does not match the ledger{hint}. Fix it or cancel.",
            [{"field": c.check, "reason": f"{c.code}: {c.token}"} for c in bad],
        )
    session.execute(
        text("""UPDATE messages SET subject = :s, body = :b, version = version + 1,
        verified_version = version + 1, guardrail_report = CAST(:rep AS jsonb), updated_at = now(),
        channel = COALESCE(CAST(:ch AS text), channel) WHERE id = CAST(:m AS uuid)"""),
        {
            "ch": channel,
            "s": subject,
            "b": body,
            "m": message_id,
            "rep": json.dumps([c.__dict__ for c in report.checks], default=str),
        },
    )
    record(
        session,
        row.customer_id,
        "edited",
        "human",
        "Draft edited and re-verified",
        ref_type="message",
        ref_id=message_id,
        actor_user_id=user_id,
    )
    return get_message(session, message_id)


def _log_refusal(session: Session, code: ErrorCode, customer_id: str, message_id: str) -> None:
    """A refusal is logged in its own transaction: the caller's transaction rolls back on the error."""
    bind = session.get_bind()
    engine: Engine = bind.engine if isinstance(bind, Connection) else bind
    with engine.begin() as c:
        c.execute(
            text("""INSERT INTO guardrail_events (check_name, code, customer_id, message_id, detail)
            VALUES ('send_gate', :c, CAST(:cu AS uuid), CAST(:m AS uuid), '{}'::jsonb)"""),
            {"c": code, "cu": customer_id, "m": message_id},
        )


def send_gate(session: Session, message_id: str) -> Any:
    """The only yes to a send: approved, current text verified, sending on, channel on, nothing disputed."""
    m = session.execute(
        text("""SELECT m.id::text, m.customer_id::text, m.status, m.version, m.verified_version,
        m.channel, m.subject, m.body, m.kind, m.last_error, m.send_attempts, c.email
        FROM messages m JOIN customers c ON c.id = m.customer_id WHERE m.id = CAST(:m AS uuid) FOR NO KEY UPDATE OF m"""),
        {"m": message_id},
    ).first()
    if m is None:
        raise AppError(ErrorCode.NOT_FOUND, "Message not found.")
    s = session.execute(text("SELECT sending_enabled, feature_whatsapp FROM settings WHERE id = 1")).one()
    reason: tuple[ErrorCode, str] | None = None
    if m.status != "approved":
        reason = (ErrorCode.NOT_APPROVED, f"Message is {m.status}, not approved.")
    elif m.verified_version != m.version:
        reason = (ErrorCode.NOT_VERIFIED, "The current text has not passed the guardrails.")
    elif not s.sending_enabled:
        reason = (ErrorCode.SENDING_DISABLED, "Sending is paused by the kill switch.")
    elif m.channel == "whatsapp" and not s.feature_whatsapp:
        reason = (ErrorCode.FEATURE_DISABLED, "WhatsApp is switched off.")
    elif (
        m.kind != "dispute_ack"
        and session.execute(
            text("""SELECT 1 FROM message_invoices mi JOIN disputes d
            ON d.invoice_id = mi.invoice_id AND d.status = 'open' WHERE mi.message_id = CAST(:m AS uuid)"""),
            {"m": message_id},
        ).scalar()
    ):
        reason = (ErrorCode.INVOICE_DISPUTED, "An invoice in this message is now disputed.")
    if reason:
        _log_refusal(session, reason[0], m.customer_id, message_id)
        raise AppError(*reason)
    return m


def request_send(session: Session, message_id: str) -> int | None:
    """MCP send_message and API: gate now, then queue the send (one job per message)."""
    send_gate(session, message_id)
    return enqueue(session.connection(), "send_message", message_id, {"message_id": message_id})


def deliver(engine: Engine, message_id: str, channels: dict[str, MessageChannel]) -> None:
    """The send worker. The claim (IN_FLIGHT) commits before delivery, so a crash can never cause a second one."""
    with engine.begin() as c, Session(bind=c) as s:
        m = s.execute(
            text("SELECT status, last_error FROM messages WHERE id = CAST(:m AS uuid) FOR NO KEY UPDATE"),
            {"m": message_id},
        ).one()
        if m.status == "sent":
            return
        if m.last_error == "IN_FLIGHT":  # a previous attempt died mid-send: never auto-retry
            s.execute(
                text(
                    "UPDATE messages SET status = 'failed', last_error = 'UNCONFIRMED' WHERE id = CAST(:m AS uuid)"
                ),
                {"m": message_id},
            )
            return
        try:
            g = send_gate(s, message_id)
        except AppError as e:
            if e.code == ErrorCode.SENDING_DISABLED:
                raise Defer from e
            if m.status != "approved":
                raise
            # A refusal after approval (a dispute, a flag turned off) is final for this approval: fail the
            # message so a collector can fix the cause and resend it. Anything not approved still raises.
            s.execute(
                text("""UPDATE messages SET status = 'failed', last_error = :e, updated_at = now()
                WHERE id = CAST(:m AS uuid)"""),
                {"e": str(e.code), "m": message_id},
            )
            return
        s.execute(
            text("""UPDATE messages SET send_attempts = send_attempts + 1, last_error = 'IN_FLIGHT'
            WHERE id = CAST(:m AS uuid)"""),
            {"m": message_id},
        )
        out = Outbound(message_id, g.email, g.subject, g.body)
        customer_id, attempts = g.customer_id, g.send_attempts + 1
    try:
        channels[g.channel].send(out)
    except ChannelError as e:
        final = attempts >= MAX_SEND_ATTEMPTS
        with engine.begin() as c, Session(bind=c) as s:
            s.execute(
                text("""UPDATE messages SET last_error = :e, status = CASE WHEN :f THEN 'failed' ELSE status END,
                updated_at = now() WHERE id = CAST(:m AS uuid)"""),
                {"e": e.code, "f": final, "m": message_id},
            )
            if final:
                record(
                    s,
                    customer_id,
                    "send_failed",
                    "system",
                    f"Send failed after {attempts} attempts ({e.code})",
                    ref_type="message",
                    ref_id=message_id,
                )
        raise
    with engine.begin() as c, Session(bind=c) as s:
        s.execute(
            text("""UPDATE messages SET status = 'sent', sent_at = now(), last_error = NULL, updated_at = now()
            WHERE id = CAST(:m AS uuid)"""),
            {"m": message_id},
        )
        record(
            s,
            customer_id,
            "sent",
            "system",
            f"{g.channel.capitalize()} sent to {g.email}",
            ref_type="message",
            ref_id=message_id,
        )


def resend(session: Session, message_id: str, user_id: str | None) -> Message:
    """A collector resends a failed or unconfirmed message by hand (US-00-011 AC3)."""
    row = _lock(session, message_id, None)
    if row.status != "failed":
        raise AppError(ErrorCode.NOT_APPROVED, "Only a failed message can be resent.")
    session.execute(
        text("""UPDATE messages SET status = 'approved', last_error = NULL, send_attempts = 0
        WHERE id = CAST(:m AS uuid)"""),
        {"m": message_id},
    )
    session.execute(
        text("DELETE FROM jobs WHERE kind = 'send_message' AND dedupe_key = :m"), {"m": message_id}
    )
    enqueue(session.connection(), "send_message", message_id, {"message_id": message_id})
    record(
        session,
        row.customer_id,
        "approved",
        "human",
        "Resend requested",
        ref_type="message",
        ref_id=message_id,
        actor_user_id=user_id,
    )
    return get_message(session, message_id)


def trusted_approve(session: Session, message_id: str) -> bool:
    """Trusted mode (US-01-016 AC3): a verified draft that meets every rule in policy trusted_mode_allow is
    approved by the system and queued; anything else waits for a human. Returns whether it was approved."""
    s = session.execute(text("SELECT autonomy_mode, feature_trusted_mode FROM settings WHERE id = 1")).one()
    if s.autonomy_mode != "trusted" or not s.feature_trusted_mode:
        return False
    rule = policy().trusted
    m = session.execute(
        text("""SELECT m.customer_id::text, m.kind, m.tone, m.channel, m.status, (m.verified_version = m.version) AS ok,
        (SELECT COALESCE(SUM(b.remaining_paise), 0) FROM message_invoices mi JOIN invoice_balances b
          ON b.invoice_id = mi.invoice_id WHERE mi.message_id = m.id) AS total,
        EXISTS (SELECT 1 FROM disputes d WHERE d.customer_id = m.customer_id AND d.status = 'open') AS disputed,
        EXISTS (SELECT 1 FROM promises p WHERE p.customer_id = m.customer_id AND p.status = 'missed') AS missed
        FROM messages m WHERE m.id = CAST(:m AS uuid)"""),
        {"m": message_id},
    ).one()
    band = priorities(session, today(session), m.customer_id)[0][2].band
    allowed = (
        m.kind == "reminder"
        and m.status == "pending_approval"
        and m.ok
        and m.tone in rule.tones
        and m.channel in rule.channels
        and band in rule.bands
        and int(m.total) <= rule.max_total_paise
        and not (rule.no_open_dispute and m.disputed)
        and not (rule.no_missed_promise and m.missed)
    )
    if not allowed:
        return False
    session.execute(
        text("""UPDATE messages SET status = 'approved', approved_at = now(), updated_at = now()
        WHERE id = CAST(:m AS uuid)"""),
        {"m": message_id},
    )
    record(
        session,
        m.customer_id,
        "approved",
        "system",
        "Auto-approved in Trusted mode (gentle reminder inside the allow-list)",
        ref_type="message",
        ref_id=message_id,
    )
    enqueue(session.connection(), "send_message", message_id, {"message_id": message_id})
    return True
