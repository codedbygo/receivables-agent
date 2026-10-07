"""Reply Understanding, Payment Verification and Escalation roles (HLD Flow B, LLD section 4).

The model reads the reply with no tools. Code validates what it returns and runs a fixed, counted tool
sequence per class; nothing the customer writes can choose a tool (REQ-068, eng review A10)."""

import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent.classify import Classification, classify, dispute_reason
from app.agent.orchestrator import MAX_CALLS, Orchestrator, Outcome, RunResult
from app.core.clock import today
from app.core.config import get_settings
from app.core.db import transaction
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.services.payments import verify_claim
from app.services.timeline import record
from app.tools.registry import ToolContext

MAX_REPLY_CHARS = 5000
ACK = (
    "Dear {name},\n\nThank you for letting us know about {invoice}. We have noted your concern, and a member of "
    "our team will contact you shortly.\n\nRegards,\nAccounts team"
)
STATEMENT = (
    "Dear {name},\n\nAs requested, here is the statement of your open invoices:\n\n{{{{invoice_table}}}}\n\n"
    "Total outstanding: {{{{total}}}}\n\nPlease reply if anything does not match your books.\n\nRegards,\n"
    "Accounts team"
)
FOLLOWUP = (
    "Dear {name},\n\nThank you for your payment. These invoices remain open:\n\n{{{{invoice_table}}}}\n\n"
    "Total outstanding: {{{{total}}}}\n\nCould you share a date for the balance?\n\nRegards,\nAccounts team"
)


@dataclass
class ReplyResult:
    reply_id: str
    classification: Classification
    run: RunResult


def ingest(session: Session, message_id: str, body: str, customer_id: str | None = None) -> tuple[str, str]:
    """Store a customer's reply against the message it answers (US-03-001). Returns (reply id, customer id)."""
    if not body.strip() or len(body) > MAX_REPLY_CHARS:
        raise AppError(ErrorCode.VALIDATION_ERROR, "The reply is empty or longer than 5,000 characters.")
    owner = session.execute(
        text("SELECT customer_id::text FROM messages WHERE id = CAST(:m AS uuid)"), {"m": message_id}
    ).scalar()
    if owner is None:
        raise AppError(ErrorCode.NOT_FOUND, "Message not found.")
    if customer_id and customer_id != owner:
        raise AppError(ErrorCode.MESSAGE_CUSTOMER_MISMATCH, "That message was sent to another customer.")
    rid = str(
        session.execute(
            text("""INSERT INTO replies (customer_id, message_id, body)
        VALUES (CAST(:c AS uuid), CAST(:m AS uuid), :b) RETURNING id::text"""),
            {"c": owner, "m": message_id, "b": body},
        ).scalar_one()
    )
    record(session, owner, "reply_received", "customer", "Reply received", ref_type="reply", ref_id=rid)
    return rid, owner


# ponytail: a bounded poll for the customer's running run; a queued reply job if runs ever take minutes.
RUN_WAIT_S = 15


def understand(o: Orchestrator, reply_id: str) -> ReplyResult:
    with o.sessions() as s:
        r = s.execute(
            text("""SELECT r.body, r.customer_id::text AS customer_id, c.name FROM replies r
            JOIN customers c ON c.id = r.customer_id WHERE r.id = CAST(:r AS uuid)"""),
            {"r": reply_id},
        ).one()
        d = today(s)
        open_invoices: list[str] = list(
            s.execute(
                text("""SELECT i.number FROM invoices i JOIN invoice_balances b
            ON b.invoice_id = i.id WHERE i.customer_id = CAST(:c AS uuid) AND b.remaining_paise > 0"""),
                {"c": r.customer_id},
            ).scalars()
        )
    started = o._start(r.customer_id, "reply")
    deadline = time.monotonic() + RUN_WAIT_S
    while started is None and time.monotonic() < deadline:  # HACK-004: a scheduled run finishes in seconds
        time.sleep(0.25)
        started = o._start(r.customer_id, "reply")
    if started is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "A run for this customer is already in progress. Try again shortly."
        )
    run_id, _ = started
    with o.failing(run_id):
        c = classify(r.body, d, open_invoices, o.gateway, run_id)
        threshold = get_settings().classify_min_confidence
        needs_review = c.injection_suspected or c.confidence < threshold or c.note == "CLASS_INVALID"
        with transaction(o.sessions) as s:
            s.execute(
                text("""UPDATE replies SET classification = :k, amount_paise = :a, stated_date = :d,
                invoice_refs = :refs, confidence = :conf, needs_review = :nr, recommended_action = :act
                WHERE id = CAST(:r AS uuid)"""),
                {
                    "k": c.klass,
                    "a": c.amount_paise,
                    "d": c.stated_date,
                    "refs": list(c.invoice_refs),
                    "conf": round(min(max(c.confidence, 0), 1), 2),
                    "nr": needs_review,
                    "act": action_for(c, needs_review),
                    "r": reply_id,
                },
            )
            bits = (
                [c.klass]
                + ([format_inr(c.amount_paise)] if c.amount_paise else [])
                + ([f"on {c.stated_date:%d %b %Y}"] if c.stated_date else [])
            )
            record(
                s,
                r.customer_id,
                "classified",
                "ai",
                " ".join(bits) + f" (confidence {c.confidence:.2f}, {c.source})",
                amount_paise=c.amount_paise,
                ref_type="reply",
                ref_id=reply_id,
            )
            if c.injection_suspected:
                s.execute(
                    text("""INSERT INTO guardrail_events (check_name, code, customer_id, agent_run_id, detail)
                    VALUES ('injection', 'PROMPT_INJECTION_SUSPECTED', CAST(:c AS uuid), CAST(:r AS uuid), '{}'::jsonb)"""),
                    {"c": r.customer_id, "r": run_id},
                )
        ctx = ToolContext(actor="ai", source="agent", run_id=run_id, max_calls=MAX_CALLS)
        reason = _act(o, run_id, ctx, reply_id, r.customer_id, r.name, c, needs_review)
        outcome: Outcome = o._outcome(run_id)
        o._finish(run_id, outcome, ctx.calls, None, None, action_for(c, needs_review), reason)
    return ReplyResult(reply_id, c, RunResult(run_id, outcome, ctx.calls, "", "", reason))


def action_for(c: Classification, needs_review: bool) -> str:
    if needs_review:
        return "escalate"
    return {
        "PROMISE": "log_promise",
        "PART_PAYMENT": "create_followup",
        "DISPUTE": "log_dispute",
        "STATEMENT_REQUEST": "send_statement",
        "PAYMENT_CONFIRMATION": "verify_payment",
    }.get(c.klass, "no_action")


def _act(
    o: Orchestrator,
    run_id: str,
    ctx: ToolContext,
    reply_id: str,
    cid: str,
    name: str,
    c: Classification,
    needs_review: bool,
) -> str:
    def call(role: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return o.invoke(run_id, ctx, role, tool, args)

    if needs_review:
        kind = "injection_suspected" if c.injection_suspected else "low_confidence"
        call(
            "escalation",
            "escalate",
            {
                "customer_id": cid,
                "kind": kind,
                "reply_id": reply_id,
                "reason": "Reply needs a human: " + kind.replace("_", " "),
            },
        )
        return f"{c.klass} needs review ({kind}); {c.note}".strip("; ")
    if c.klass == "PROMISE":
        if c.amount_paise is None or c.stated_date is None:
            call(
                "escalation",
                "escalate",
                {
                    "customer_id": cid,
                    "kind": "low_confidence",
                    "reply_id": reply_id,
                    "reason": "Promise without a clear amount or date",
                },
            )
            return "promise without amount or date; escalated"
        call(
            "reply_understanding",
            "log_promise",
            {
                "customer_id": cid,
                "amount_paise": c.amount_paise,
                "promised_date": c.stated_date.isoformat(),
                "reply_id": reply_id,
                **({"invoice_numbers": list(c.invoice_refs)} if c.invoice_refs else {}),
            },
        )
    elif c.klass == "DISPUTE":
        invoice = c.invoice_refs[0] if c.invoice_refs else None
        if invoice is None:
            call(
                "escalation",
                "escalate",
                {
                    "customer_id": cid,
                    "kind": "dispute",
                    "reply_id": reply_id,
                    "reason": "Dispute without an invoice number: pick the invoice",
                },
            )
            return "dispute without invoice; escalated"
        d = call(
            "reply_understanding",
            "log_dispute",
            {
                "customer_id": cid,
                "invoice_number": invoice,
                "reason": _reason(o, reply_id),
                "reply_id": reply_id,
            },
        )
        call(
            "escalation",
            "escalate",
            {
                "customer_id": cid,
                "kind": "dispute",
                "reply_id": reply_id,
                "reason": f"{invoice} disputed",
                **({"dispute_id": d["data"]["id"]} if d.get("ok") else {}),
            },
        )
        call(
            "reply_understanding",
            "draft_message",
            {
                "customer_id": cid,
                "kind": "dispute_ack",
                "tone": "gentle",
                "prose": ACK.format(name=name, invoice=invoice),
                "invoice_numbers": [invoice],
            },
        )
    elif c.klass == "STATEMENT_REQUEST":
        call(
            "reply_understanding",
            "draft_message",
            {"customer_id": cid, "kind": "statement", "tone": "gentle", "prose": STATEMENT.format(name=name)},
        )
    elif c.klass == "PART_PAYMENT":
        call("reply_understanding", "check_promise_status", {"customer_id": cid})
        call(
            "reply_understanding",
            "create_followup",
            {"customer_id": cid, "prose": FOLLOWUP.format(name=name)},
        )
    elif c.klass == "PAYMENT_CONFIRMATION":
        with o.sessions() as s:
            match = verify_claim(s, cid, c.amount_paise, c.stated_date)
        if match is None:  # never mark paid on a claim (REQ-078)
            call(
                "escalation",
                "escalate",
                {
                    "customer_id": cid,
                    "kind": "claim_not_found",
                    "reply_id": reply_id,
                    "reason": "Payment claim not found in the ledger",
                },
            )
            return "claim not in the ledger; escalated"
        return f"claim matches ledger payment {match}"
    return f"{c.klass} ({c.source})" + (f"; {c.note}" if c.note else "")


def _reason(o: Orchestrator, reply_id: str) -> str:
    with o.sessions() as s:
        body = str(
            s.execute(text("SELECT body FROM replies WHERE id = CAST(:r AS uuid)"), {"r": reply_id}).scalar()
        )
    return dispute_reason(json.dumps(body)[1:-1])
