"""The SIMULATED payment link (US-03-004, REQ-088): a signed link for one invoice; paying it posts through the
same ledger path as the bank feed. The token is the invoice number plus an HMAC, so it cannot be guessed."""

import hashlib
import hmac
import time
import uuid

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.services import payments


class PayLink(BaseModel):
    invoice_number: str
    customer_name: str
    amount_paise: int
    simulated: bool = True


class LinkOut(BaseModel):
    token: str
    invoice_number: str


_READ = """SELECT i.number, c.name, b.remaining_paise FROM invoices i JOIN customers c ON c.id = i.customer_id
    JOIN invoice_balances b ON b.invoice_id = i.id WHERE i.number = :n"""
TTL_SECONDS = 7 * 24 * 3600  # a forwarded link stops working after a week (T-41)


def _sig(secret: str, number: str, exp: str) -> str:
    return hmac.new(secret.encode(), f"paylink:{number}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def _enabled(session: Session) -> None:
    if not session.execute(text("SELECT feature_payment_link FROM settings WHERE id = 1")).scalar():
        raise AppError(ErrorCode.FEATURE_DISABLED, "Payment links are switched off.")


def create(session: Session, secret: str, number: str, now: float | None = None) -> LinkOut:
    _enabled(session)
    if not session.execute(text("SELECT 1 FROM invoices WHERE number = :n"), {"n": number}).scalar():
        raise AppError(ErrorCode.INVOICE_NOT_FOUND, f"{number} does not exist.")
    exp = str(int((now if now is not None else time.time()) + TTL_SECONDS))
    return LinkOut(token=f"{number}.{exp}.{_sig(secret, number, exp)}", invoice_number=number)


def _open(session: Session, secret: str, token: str, lock: bool) -> PayLink:
    _enabled(session)
    number, _, rest = token.partition(".")
    exp, _, sig = rest.partition(".")
    if not (exp.isdigit() and hmac.compare_digest(_sig(secret, number, exp), sig)) or time.time() > int(exp):
        raise AppError(ErrorCode.NOT_FOUND, "This payment link is not valid.")
    if lock:  # lock first, read the balance in a new statement, so a second click sees the first payment
        session.execute(text("SELECT 1 FROM invoices WHERE number = :n FOR UPDATE"), {"n": number})
    r = session.execute(text(_READ), {"n": number}).one()
    return PayLink(invoice_number=r.number, customer_name=r.name, amount_paise=r.remaining_paise)


def read(session: Session, secret: str, token: str) -> PayLink:
    return _open(session, secret, token, lock=False)


def pay(session: Session, secret: str, token: str) -> payments.Payment:
    link = _open(session, secret, token, lock=True)  # the row lock makes a double click pay once
    if link.amount_paise <= 0:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"{link.invoice_number} is already paid.")
    credit = payments.BankCredit(
        event_id=f"paylink-{uuid.uuid4()}",
        amount_paise=link.amount_paise,
        reference=f"PAYLINK {link.invoice_number}",
        payer_name=link.customer_name,
    )
    return payments.receive_credit(session, credit, source="payment_link")
