"""The customer payment portal (HACK-003 F6).

A collector creates a link for one customer. The token is 256 random bits shown once; the database keeps only its
SHA-256, an expiry, a revocation time and a write counter. Every portal call resolves the token to exactly that one
customer and touches nothing else. The public view is its own model with an allow-listed set of fields: no notes,
no risk score, no AI reasoning, no timeline, no other customer. Portal text is untrusted customer input."""

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent.classify import dispute_reason, injection_suspected
from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.services import collections, ledger, paylink
from app.services.timeline import record

TTL_DAYS = 7
MAX_WRITES = 20
MAX_TEXT = 500
PROMISE_WINDOW_DAYS = 60
INVALID = "This link is not valid. Ask your account manager for a new one."


class PortalInvoice(BaseModel):
    number: str
    invoice_date: date
    due_date: date
    remaining_paise: int
    status: Literal["open", "overdue", "under review"]


class PortalPromise(BaseModel):
    amount_paise: int
    promised_date: date


class PortalView(BaseModel):
    """Everything the public page may show. Adding a field here is a security review item."""

    customer_name: str
    outstanding_paise: int
    invoices: list[PortalInvoice]
    promises: list[PortalPromise]
    pay_now_available: bool
    payment_simulated: bool
    expires_at: datetime


class LinkOut(BaseModel):
    token: str
    path: str
    expires_at: datetime


class PortalAck(BaseModel):
    ok: bool
    message: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_link(session: Session, customer_id: str, user_id: str) -> LinkOut:
    ledger.get_customer(session, today(session), customer_id)  # 404 for an unknown customer
    token = secrets.token_urlsafe(32)
    expires: datetime = session.execute(
        text("""INSERT INTO portal_links (customer_id, token_sha256, created_by, expires_at)
        VALUES (CAST(:c AS uuid), :h, CAST(:u AS uuid), now() + make_interval(days => :d)) RETURNING expires_at"""),
        {"c": customer_id, "h": _hash(token), "u": user_id, "d": TTL_DAYS},
    ).scalar_one()
    record(
        session,
        customer_id,
        "portal_link_created",
        "human",
        f"Customer portal link created, valid {TTL_DAYS} days",
        actor_user_id=user_id,
    )
    return LinkOut(token=token, path=f"#/portal/{token}", expires_at=expires)


def revoke_links(session: Session, customer_id: str, user_id: str) -> int:
    n = len(
        session.execute(
            text("""UPDATE portal_links SET revoked_at = now() WHERE customer_id = CAST(:c AS uuid)
            AND revoked_at IS NULL AND expires_at > now() RETURNING id"""),
            {"c": customer_id},
        ).all()
    )
    if n:
        record(
            session,
            customer_id,
            "portal_link_revoked",
            "human",
            f"{n} portal link(s) revoked",
            actor_user_id=user_id,
        )
    return n


_READ = """SELECT id::text, customer_id::text, expires_at, writes FROM portal_links WHERE token_sha256 = :h
    AND revoked_at IS NULL AND expires_at > now()"""
_LOCK = _READ + " FOR UPDATE"


def _own_invoice(session: Session, customer_id: str, number: str) -> None:
    """Unknown and another customer's invoice get the same answer, so the portal reveals nothing about others."""
    owner = session.execute(
        text("SELECT customer_id::text FROM invoices WHERE number = :n"), {"n": number}
    ).scalar()
    if owner != customer_id:
        raise AppError(ErrorCode.NOT_FOUND, "Invoice not found.")


def _open(session: Session, token: str, write: bool) -> tuple[str, str, datetime]:
    """(link id, customer id, expires_at) for a live link, or the same 404 for unknown, expired and revoked."""
    if not token or len(token) > 100:
        raise AppError(ErrorCode.NOT_FOUND, INVALID)
    r = session.execute(text(_LOCK if write else _READ), {"h": _hash(token)}).first()
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, INVALID)
    if write and r.writes >= MAX_WRITES:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "Too many requests on this link. Please contact us directly."
        )
    session.execute(
        text(
            "UPDATE portal_links SET last_used_at = now(), writes = writes + :w WHERE id = CAST(:i AS uuid)"
        ),
        {"w": 1 if write else 0, "i": r.id},
    )
    return str(r.id), str(r.customer_id), r.expires_at


def view(session: Session, token: str) -> PortalView:
    _, cid, expires = _open(session, token, write=False)
    d = today(session)
    c = ledger.get_customer(session, d, cid)
    open_ = [i for i in ledger.customer_invoices(session, d, cid) if i.remaining_paise > 0]
    promises = session.execute(
        text("""SELECT amount_paise, promised_date FROM promises WHERE customer_id = CAST(:c AS uuid)
        AND status = 'pending' ORDER BY promised_date"""),
        {"c": cid},
    ).all()
    link_on = bool(session.execute(text("SELECT feature_payment_link FROM settings WHERE id = 1")).scalar())
    return PortalView(
        customer_name=c.name,
        outstanding_paise=sum(i.remaining_paise for i in open_),
        invoices=[
            PortalInvoice(
                number=i.number,
                invoice_date=i.invoice_date,
                due_date=i.due_date,
                remaining_paise=i.remaining_paise,
                status="under review" if i.status == "disputed" else "overdue" if i.due_date < d else "open",
            )
            for i in open_
        ],
        promises=[
            PortalPromise(amount_paise=p.amount_paise, promised_date=p.promised_date) for p in promises
        ],
        pay_now_available=link_on,
        payment_simulated=True,  # no payment processor is connected; the page says so
        expires_at=expires,
    )


def _check_text(session: Session, customer_id: str, said: str) -> str:
    said = said.strip()
    if not said or len(said) > MAX_TEXT:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Please write 1 to {MAX_TEXT} characters.")
    if injection_suspected(said):
        session.execute(
            text("""INSERT INTO guardrail_events (check_name, code, customer_id, detail)
            VALUES ('injection', 'PROMPT_INJECTION_SUSPECTED', CAST(:c AS uuid), '{"source": "portal"}'::jsonb)"""),
            {"c": customer_id},
        )
        collections.escalate(
            session, customer_id, "injection_suspected", "Instruction-like text sent from the portal"
        )
    return said


def promise(session: Session, token: str, amount_paise: int, promised_date: date) -> PortalAck:
    _, cid, _ = _open(session, token, write=True)
    d = today(session)
    chase = sum(
        i.remaining_paise
        for i in ledger.customer_invoices(session, d, cid)
        if i.remaining_paise > 0 and i.status != "disputed"
    )
    if not 0 < amount_paise <= chase:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Enter an amount up to the open balance.")
    if not d <= promised_date <= d + timedelta(days=PROMISE_WINDOW_DAYS):
        raise AppError(
            ErrorCode.VALIDATION_ERROR, f"Choose a date within the next {PROMISE_WINDOW_DAYS} days."
        )
    collections.log_promise(session, cid, amount_paise, promised_date, actor="customer")
    return PortalAck(ok=True, message="Thank you. Your promise is recorded.")


def dispute(session: Session, token: str, invoice_number: str, description: str) -> PortalAck:
    _, cid, _ = _open(session, token, write=True)
    said = _check_text(session, cid, description)
    if injection_suspected(
        said
    ):  # escalated in _check_text; no dispute is created from instruction-like text
        return PortalAck(ok=True, message="Thank you. A member of our team will contact you.")
    _own_invoice(session, cid, invoice_number)
    collections.log_dispute(session, cid, invoice_number, dispute_reason(said), actor="customer")
    return PortalAck(ok=True, message=f"Thank you. Your query on {invoice_number} is with our team.")


def help_request(session: Session, token: str, message: str) -> PortalAck:
    _, cid, _ = _open(session, token, write=True)
    said = _check_text(session, cid, message)
    if not injection_suspected(said):
        collections.escalate(session, cid, "low_confidence", f"Portal help request: {said}"[:300])
    return PortalAck(ok=True, message="Thank you. A member of our team will contact you.")


def pay(session: Session, token: str, secret: str, invoice_number: str) -> PortalAck:
    """Pay Now: the SIMULATED payment link path for one of this customer's invoices."""
    _, cid, _ = _open(session, token, write=True)
    _own_invoice(session, cid, invoice_number)
    link = paylink.create(session, secret, invoice_number)
    paid = paylink.pay(session, secret, link.token)
    return PortalAck(
        ok=True,
        message=f"SIMULATED payment of {format_inr(paid.amount_paise)} recorded for {invoice_number}.",
    )
