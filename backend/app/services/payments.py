"""Payments, allocation, promises and the demo clock (US-00-017 to US-00-021, US-01-004, REQ-076 to REQ-080).

Money enters the ledger only as a payment row: from the signed bank feed, the payment link, or a
collector matching a credit. A customer's claim never marks anything paid (REQ-078)."""

import hashlib
import hmac
import json
import re
import time
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.services import followups
from app.services.collections import escalate
from app.services.timeline import record

INVOICE = re.compile(r"\bINV-\d+\b")
REPLAY_WINDOW_S = 300
CLAIM_WINDOW_DAYS = 7


class BankCredit(BaseModel):
    event_id: str
    amount_paise: int
    reference: str
    payer_name: str = ""
    occurred_at: str = ""


class Allocation(BaseModel):
    invoice_id: str
    invoice_number: str
    amount_paise: int


class Payment(BaseModel):
    id: str
    customer_id: str | None
    amount_paise: int
    received_on: date
    reference: str | None
    source: str
    match_status: str
    allocations: list[Allocation]


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str, timestamp: str, signature: str, body: bytes, now: float | None = None
) -> None:
    """HMAC over '<timestamp>.<body>' and a 300 s replay window (REQ-116, T-08)."""
    if not secret or not hmac.compare_digest(
        sign(secret, timestamp, body).encode(), (signature or "").encode()
    ):
        raise AppError(ErrorCode.SIGNATURE_INVALID, "Bad signature.")
    try:
        age = abs((now or time.time()) - int(timestamp))
    except ValueError as e:
        raise AppError(ErrorCode.REPLAY_WINDOW, "Bad timestamp.") from e
    if age > REPLAY_WINDOW_S:
        raise AppError(ErrorCode.REPLAY_WINDOW, "Timestamp outside the replay window.")


def get_payment(session: Session, payment_id: str) -> Payment:
    p = (
        session.execute(
            text("""SELECT id::text, customer_id::text, amount_paise, received_on, reference, source,
        match_status FROM payments WHERE id = CAST(:p AS uuid)"""),
            {"p": payment_id},
        )
        .mappings()
        .one()
    )
    allocs = [
        Allocation(**a)
        for a in session.execute(
            text("""SELECT a.invoice_id::text, i.number AS invoice_number,
        a.amount_paise FROM payment_allocations a JOIN invoices i ON i.id = a.invoice_id
        WHERE a.payment_id = CAST(:p AS uuid) ORDER BY i.due_date"""),
            {"p": payment_id},
        ).mappings()
    ]
    return Payment(**p, allocations=allocs)


def _candidates(session: Session, reference: str, payer: str) -> list[str]:
    """Customers the credit could belong to: an invoice named in the reference, else a name match."""
    numbers = INVOICE.findall(reference)
    if numbers:
        return list(
            session.execute(
                text("SELECT DISTINCT customer_id::text FROM invoices WHERE number = ANY(:n)"), {"n": numbers}
            ).scalars()
        )
    haystack = f" {re.sub(r'[^a-z0-9]+', ' ', (reference + ' ' + payer).lower())} "
    names = session.execute(text("SELECT id::text, name FROM customers")).all()
    return [r.id for r in names if f" {re.sub(r'[^a-z0-9]+', ' ', r.name.lower()).strip()} " in haystack]


def receive_credit(
    session: Session, credit: BankCredit, source: Literal["bank_feed", "payment_link"] = "bank_feed"
) -> Payment:
    """One bank credit into the ledger: dedupe, match a unique customer, allocate, settle promises."""
    existing = session.execute(
        text("SELECT id::text FROM payments WHERE bank_event_id = :e"), {"e": credit.event_id}
    ).scalar()
    if existing:
        return get_payment(session, existing)  # a replayed event changes nothing (T-09)
    if credit.amount_paise <= 0:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Enter an amount above ₹0.")
    d = today(session)
    matches = _candidates(session, credit.reference, credit.payer_name)
    customer = matches[0] if len(matches) == 1 else None
    inserted = session.execute(
        text("""INSERT INTO payments (customer_id, amount_paise, received_on, reference, source,
        bank_event_id, match_status) VALUES (CAST(:c AS uuid), :a, :d, :r, :src, :e, :m)
        ON CONFLICT (bank_event_id) WHERE bank_event_id IS NOT NULL DO NOTHING RETURNING id::text"""),
        {
            "src": source,
            "c": customer,
            "a": credit.amount_paise,
            "d": d,
            "r": credit.reference,
            "e": credit.event_id,
            "m": "matched" if customer else "needs_verification",
        },
    ).scalar()
    if inserted is None:  # a concurrent delivery of the same event won the race: same answer as a replay
        return get_payment(
            session,
            str(
                session.execute(
                    text("SELECT id::text FROM payments WHERE bank_event_id = :e"), {"e": credit.event_id}
                ).scalar_one()
            ),
        )
    pid = str(inserted)
    if customer is None:  # ambiguous or unknown: a human decides (AC-US-00-017-2)
        for c in matches[:1]:
            escalate(
                session,
                c,
                "payment_needs_verification",
                f"Credit {format_inr(credit.amount_paise)} matches {len(matches)} customers",
                payment_id=pid,
            )
        return get_payment(session, pid)
    record(
        session,
        customer,
        "payment_received",
        "system",
        f"Bank credit {credit.reference}",
        amount_paise=credit.amount_paise,
        ref_type="payment",
        ref_id=pid,
    )
    allocate(session, pid)
    return get_payment(session, pid)


def match_payment(session: Session, payment_id: str, customer_id: str) -> Payment:
    """A collector assigns a credit that needed verification."""
    p = session.execute(
        text("SELECT match_status FROM payments WHERE id = CAST(:p AS uuid) FOR UPDATE"), {"p": payment_id}
    ).scalar()
    if p is None:
        raise AppError(ErrorCode.NOT_FOUND, "Payment not found.")
    if p != "needs_verification":
        raise AppError(ErrorCode.VALIDATION_ERROR, "This payment is already matched.")
    session.execute(
        text("""UPDATE payments SET customer_id = CAST(:c AS uuid), match_status = 'matched'
        WHERE id = CAST(:p AS uuid)"""),
        {"c": customer_id, "p": payment_id},
    )
    pay = get_payment(session, payment_id)
    record(
        session,
        customer_id,
        "payment_received",
        "human",
        f"Credit {pay.reference} matched by a collector",
        amount_paise=pay.amount_paise,
        ref_type="payment",
        ref_id=payment_id,
    )
    allocate(session, payment_id)
    return get_payment(session, payment_id)


def allocate(session: Session, payment_id: str) -> None:
    """Referenced invoice first, then oldest due first among open, undisputed invoices (Q-012).
    Statuses follow the balances; any excess stays unallocated and is escalated."""
    pay = get_payment(session, payment_id)
    assert pay.customer_id is not None
    left = pay.amount_paise
    named = INVOICE.findall(pay.reference or "")
    # Serialise credits for one customer: the balances below are read after the lock, in a new statement.
    session.execute(
        text("SELECT 1 FROM invoices WHERE customer_id = CAST(:c AS uuid) FOR UPDATE"), {"c": pay.customer_id}
    )
    rows = session.execute(
        text("""SELECT i.id::text, i.number, b.remaining_paise FROM invoices i
        JOIN invoice_balances b ON b.invoice_id = i.id WHERE i.customer_id = CAST(:c AS uuid)
        AND b.remaining_paise > 0 AND i.status <> 'disputed' ORDER BY i.due_date, i.number"""),
        {"c": pay.customer_id},
    ).all()
    rows = sorted(
        rows, key=lambda r: r.number not in named
    )  # stable: named first, then the oldest-first order
    for r in rows:
        if left <= 0:
            break
        part = min(left, r.remaining_paise)
        session.execute(
            text("""INSERT INTO payment_allocations (payment_id, invoice_id, amount_paise)
            VALUES (CAST(:p AS uuid), CAST(:i AS uuid), :a)"""),
            {"p": payment_id, "i": r.id, "a": part},
        )
        session.execute(
            text("""UPDATE invoices i SET status = CASE WHEN b.remaining_paise = 0 THEN 'paid'
            ELSE 'partially_paid' END, updated_at = now() FROM invoice_balances b
            WHERE b.invoice_id = i.id AND i.id = CAST(:i AS uuid)"""),
            {"i": r.id},
        )
        record(
            session,
            pay.customer_id,
            "payment_matched",
            "system",
            f"Matched to {r.number}",
            amount_paise=part,
            ref_type="payment",
            ref_id=payment_id,
        )
        left -= part
    if left > 0:
        escalate(
            session,
            pay.customer_id,
            "payment_needs_verification",
            f"{format_inr(left)} of the credit is not allocated to any open invoice",
            payment_id=payment_id,
        )
    evaluate_promises(session, pay.customer_id)


def evaluate_promises(session: Session, customer_id: str) -> None:
    """Pending promises settle against matched payments logged after the promise and received by its date;
    a promise whose date has passed is partially fulfilled or missed (Q-004, no grace days)."""
    d = today(session)
    promises = session.execute(
        text("""SELECT id::text, amount_paise, promised_date, created_at FROM promises
        WHERE customer_id = CAST(:c AS uuid) AND status = 'pending' ORDER BY promised_date, created_at FOR UPDATE"""),
        {"c": customer_id},
    ).all()
    # ponytail: earlier promises consume payments first, within this evaluation only; a credit that settled a
    # promise in an earlier evaluation is excluded by created_at. Per-payment allocation to promises if that leaks.
    used = 0
    for p in promises:
        paid: int = session.execute(
            text("""SELECT COALESCE(SUM(amount_paise), 0) FROM payments
            WHERE customer_id = CAST(:c AS uuid) AND match_status = 'matched' AND received_on <= :pd
            AND created_at >= :made"""),
            {"c": customer_id, "pd": p.promised_date, "made": p.created_at},
        ).scalar_one()
        paid = max(paid - used, 0)
        used += min(paid, p.amount_paise)
        if paid >= p.amount_paise:
            status, kind = "fulfilled", "promise_fulfilled"
        elif d > p.promised_date:
            status, kind = (
                ("partially_fulfilled", "promise_partially_fulfilled")
                if paid
                else ("missed", "promise_missed")
            )
        else:
            continue
        session.execute(
            text("UPDATE promises SET status = :s, resolved_at = now() WHERE id = CAST(:p AS uuid)"),
            {"s": status, "p": p.id},
        )
        record(
            session,
            customer_id,
            kind,
            "system",
            f"Promise of {format_inr(p.amount_paise)} for {p.promised_date:%d %b %Y} {status.replace('_', ' ')}",
            amount_paise=p.amount_paise,
            ref_type="promise",
            ref_id=p.id,
        )
        if status != "fulfilled":  # HACK-003 F5: the follow-up task, and a draft outside Manual mode
            followups.on_broken_promise(
                session, customer_id, p.id, "missed_promise" if status == "missed" else "partial_promise"
            )


def check_promises(engine: Engine) -> None:
    """The promise-check job: every customer with a pending promise."""
    with engine.begin() as c, Session(bind=c) as s:
        pending: list[str] = list(
            s.execute(
                text("SELECT DISTINCT customer_id::text FROM promises WHERE status = 'pending'")
            ).scalars()
        )
        for cid in pending:
            evaluate_promises(s, cid)


def verify_claim(
    session: Session, customer_id: str, amount_paise: int | None, claimed_on: date | None
) -> str | None:
    """A 'we already paid' reply: the matching ledger payment id, or None (REQ-076). Never creates a payment."""
    anchor = claimed_on or today(session)
    return session.execute(
        text("""SELECT id::text FROM payments WHERE customer_id = CAST(:c AS uuid)
        AND match_status = 'matched' AND received_on BETWEEN :lo AND :hi
        AND (CAST(:a AS bigint) IS NULL OR amount_paise = :a) ORDER BY received_on DESC LIMIT 1"""),
        {
            "c": customer_id,
            "a": amount_paise,
            "lo": anchor - timedelta(days=CLAIM_WINDOW_DAYS),
            "hi": anchor + timedelta(days=CLAIM_WINDOW_DAYS),
        },
    ).scalar()


def advance_clock(session: Session, days: int) -> date:
    if not 1 <= days <= 60:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Choose between 1 and 60 days.")
    new: date = session.execute(
        text("""UPDATE settings SET demo_today = demo_today + :n, updated_at = now() WHERE id = 1
        RETURNING demo_today"""),
        {"n": days},
    ).scalar_one()
    pending: list[str] = list(
        session.execute(
            text("SELECT DISTINCT customer_id::text FROM promises WHERE status = 'pending'")
        ).scalars()
    )
    for cid in pending:  # the move is shown where it matters: customers whose promises it checks
        record(session, cid, "clock_advanced", "human", f"Demo clock advanced {days} days to {new:%d %b %Y}")
        evaluate_promises(session, cid)
    return new


def signed_credit(secret: str, credit: BankCredit) -> tuple[str, str, bytes]:
    """The admin 'simulate credit' path signs server-side and goes through the same handler (HLD Flow C)."""
    body = json.dumps(credit.model_dump()).encode()
    ts = str(int(time.time()))
    return ts, sign(secret, ts, body), body


def check_promise(session: Session, promise_id: str) -> tuple[str, list[str], str]:
    """[Check payment] on a promise: settle it against the ledger now; (customer id, payment ids, message)."""
    p = session.execute(
        text("""SELECT customer_id::text, amount_paise, promised_date, created_at FROM promises
        WHERE id = CAST(:p AS uuid)"""),
        {"p": promise_id},
    ).first()
    if p is None:
        raise AppError(ErrorCode.NOT_FOUND, "Promise not found.")
    evaluate_promises(session, p.customer_id)
    rows = session.execute(
        text("""SELECT id::text, amount_paise FROM payments WHERE customer_id = CAST(:c AS uuid)
        AND match_status = 'matched' AND received_on <= :pd AND created_at >= :made ORDER BY received_on"""),
        {"c": p.customer_id, "pd": p.promised_date, "made": p.created_at},
    ).all()
    paid = sum(r.amount_paise for r in rows)
    message = f"Payment of {format_inr(paid)} matched" if paid else "No matching payment yet"
    return p.customer_id, [r.id for r in rows], message
