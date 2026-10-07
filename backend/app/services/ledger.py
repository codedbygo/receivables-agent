"""Ledger reads (US-00-001): balances come from invoice_balances, dates from the demo clock."""

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.services import overview
from app.services.priority import priorities

InvoiceStatus = Literal["unpaid", "partially_paid", "paid", "disputed"]


class Customer(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    segment: str
    credit_terms_days: int
    outstanding_paise: int
    overdue_paise: int
    band: Literal["HIGH", "MEDIUM", "LOW"] | None
    last_contact_at: date | None
    next_action: str | None


class Invoice(BaseModel):
    id: str
    number: str
    invoice_date: date
    due_date: date
    amount_paise: int
    paid_paise: int
    remaining_paise: int
    status: InvoiceStatus
    days_overdue: int


_CUSTOMERS = text("""
SELECT c.id::text AS id, c.name, c.email, c.phone, c.segment, c.credit_terms_days,
  COALESCE(SUM(b.remaining_paise), 0) AS outstanding,
  COALESCE(SUM(b.remaining_paise) FILTER (WHERE i.due_date < :today), 0) AS overdue,
  (SELECT max(t.business_date) FROM timeline_events t WHERE t.customer_id = c.id AND t.kind = 'sent')
    AS last_contact_at  -- the demo clock's date, as on the customer page (tenet 5, HACK-004)
FROM customers c
LEFT JOIN invoices i ON i.customer_id = c.id
LEFT JOIN invoice_balances b ON b.invoice_id = i.id
WHERE (CAST(:cid AS uuid) IS NULL OR c.id = CAST(:cid AS uuid))
GROUP BY c.id
ORDER BY c.name
LIMIT :limit
""")

_INVOICES = text("""
SELECT i.id::text AS id, i.number, i.invoice_date, i.due_date, i.amount_paise,
  b.paid_paise, b.remaining_paise,
  i.status, GREATEST(:today - i.due_date, 0) AS days_overdue
FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id
WHERE i.customer_id = CAST(:cid AS uuid) AND (CAST(:status AS text) IS NULL OR i.status = :status)
ORDER BY i.due_date, i.number
LIMIT :limit
""")


def list_customers(
    session: Session, today: date, limit: int = 100, customer_id: str | None = None
) -> list[Customer]:
    bands = {cid: p.band if p.score > 0 else None for cid, _, p in priorities(session, today, customer_id)}
    rows = session.execute(_CUSTOMERS, {"today": today, "cid": customer_id, "limit": limit}).mappings()
    return [
        Customer(
            **{
                k: r[k]
                for k in ("id", "name", "email", "phone", "segment", "credit_terms_days", "last_contact_at")
            },
            outstanding_paise=r["outstanding"],
            overdue_paise=r["overdue"],
            band=bands.get(r["id"]),
            next_action=overview.next_action(session, r["id"], today),
        )  # ponytail: one rules query per row (list capped at limit); one set-based query if the list grows
        for r in rows
    ]


def get_customer(session: Session, today: date, customer_id: str) -> Customer:
    found = list_customers(session, today, 1, customer_id)
    if not found:
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    return found[0]


def customer_invoices(
    session: Session, today: date, customer_id: str, status: str | None = None, limit: int = 100
) -> list[Invoice]:
    get_customer(session, today, customer_id)
    rows = session.execute(_INVOICES, {"today": today, "cid": customer_id, "status": status, "limit": limit})
    return [Invoice(**r) for r in rows.mappings()]
