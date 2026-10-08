"""Distributors and invoices a collector manages in the console (HACK-007): create, edit, delete, add an invoice,
and a CSV upload of both. Balances still come only from the ledger (tenet 1): an invoice is born unpaid."""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.services.timeline import record

EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[a-z]{2,}$", re.I)
Segment = Literal["enterprise", "mid_market", "sme"]
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 500
COLUMNS = (
    "customer_name",
    "email",
    "phone",
    "segment",
    "credit_terms_days",
    "invoice_number",
    "invoice_date",
    "due_date",
    "amount_rupees",
)


def _email(v: str) -> str:
    v = v.strip()
    if not EMAIL.match(v):
        raise ValueError("Enter an email address like accounts@example.com.")
    return v


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Email = Annotated[str, Field(max_length=254), AfterValidator(_email)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Terms = Annotated[int, Field(ge=0, le=365)]
Number = Annotated[str, Field(pattern=r"^INV-\d{1,12}$")]


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    email: Email
    phone: Phone = ""
    segment: Segment = "sme"
    credit_terms_days: Terms = 30


class CustomerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    email: Email | None = None
    phone: Phone | None = None
    segment: Segment | None = None
    credit_terms_days: Terms | None = None


class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: Number
    invoice_date: date
    due_date: date
    amount_paise: Annotated[int, Field(gt=0, le=10_000_000_000_00)]  # up to ₹1,000 crore

    @model_validator(mode="after")
    def _dates(self) -> "InvoiceIn":
        if self.due_date < self.invoice_date:
            raise ValueError("The due date is before the invoice date.")
        return self


class Deleted(BaseModel):
    id: str
    name: str


class Imported(BaseModel):
    customers_created: int
    invoices_added: int


def _no_name_clash(session: Session, name: str, except_id: str | None = None) -> None:
    clash = session.execute(
        text("""SELECT 1 FROM customers WHERE lower(name) = lower(:n)
        AND (CAST(:id AS uuid) IS NULL OR id <> CAST(:id AS uuid))"""),
        {"n": name, "id": except_id},
    ).first()
    if clash:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"A customer named {name} already exists.")


def create_customer(session: Session, body: CustomerIn, user_id: str) -> str:
    _no_name_clash(session, body.name)
    cid: str = session.execute(
        text("""INSERT INTO customers (name, email, phone, segment, credit_terms_days)
        VALUES (:name, :email, :phone, :segment, :credit_terms_days) RETURNING id::text"""),
        body.model_dump(),
    ).scalar_one()
    record(session, cid, "customer_created", "human", f"Customer {body.name} created", actor_user_id=user_id)
    return cid


def update_customer(session: Session, customer_id: str, patch: CustomerPatch, user_id: str) -> None:
    changes = patch.model_dump(exclude_none=True)
    if not session.execute(
        text("SELECT 1 FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id}
    ).first():
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    if not changes:
        return
    if "name" in changes:
        _no_name_clash(session, changes["name"], customer_id)
    session.execute(  # a field left out of the patch keeps its value
        text("""UPDATE customers SET name = COALESCE(:name, name), email = COALESCE(:email, email),
        phone = COALESCE(:phone, phone), segment = COALESCE(:segment, segment),
        credit_terms_days = COALESCE(:credit_terms_days, credit_terms_days) WHERE id = CAST(:cid AS uuid)"""),
        {**patch.model_dump(), "cid": customer_id},
    )
    fields = ", ".join(k.replace("_", " ") for k in changes)
    record(
        session, customer_id, "customer_updated", "human", f"Details changed: {fields}", actor_user_id=user_id
    )


# Every row that points at the customer, children before parents (most foreign keys are RESTRICT). Notes, portal
# links and timeline events cascade; guardrail events keep their row with the customer set to NULL.
_DELETE = [
    """DELETE FROM jobs WHERE kind = 'send_message' AND status = 'queued'
       AND payload->>'message_id' IN (SELECT id::text FROM messages WHERE customer_id = CAST(:c AS uuid))""",
    "DELETE FROM follow_up_tasks WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM calls WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM escalations WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM disputes WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM promises WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM replies WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM messages WHERE customer_id = CAST(:c AS uuid)",
    """DELETE FROM payment_allocations WHERE invoice_id IN
       (SELECT id FROM invoices WHERE customer_id = CAST(:c AS uuid))""",
    "DELETE FROM payments WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM invoices WHERE customer_id = CAST(:c AS uuid)",
    "DELETE FROM agent_runs WHERE customer_id = CAST(:c AS uuid)",
]


def delete_customer(session: Session, customer_id: str) -> Deleted:
    """The customer and everything recorded about them, in one transaction (the caller's)."""
    name = session.execute(
        text("SELECT name FROM customers WHERE id = CAST(:c AS uuid) FOR UPDATE"), {"c": customer_id}
    ).scalar()
    if name is None:
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    for sql in _DELETE:
        session.execute(text(sql), {"c": customer_id})
    session.execute(text("DELETE FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id})
    return Deleted(id=customer_id, name=name)


def add_invoice(session: Session, customer_id: str, body: InvoiceIn, user_id: str) -> str:
    if not session.execute(
        text("SELECT 1 FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id}
    ).first():
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    if session.execute(text("SELECT 1 FROM invoices WHERE number = :n"), {"n": body.number}).first():
        raise AppError(ErrorCode.VALIDATION_ERROR, f"{body.number} already exists.")
    iid: str = session.execute(
        text("""INSERT INTO invoices (customer_id, number, invoice_date, due_date, amount_paise)
        VALUES (CAST(:c AS uuid), :number, :invoice_date, :due_date, :amount_paise) RETURNING id::text"""),
        {"c": customer_id, **body.model_dump()},
    ).scalar_one()
    record(
        session,
        customer_id,
        "invoice_added",
        "human",
        f"{body.number} added: {format_inr(body.amount_paise)} due {body.due_date:%d %b %Y}",
        amount_paise=body.amount_paise,
        ref_type="invoice",
        ref_id=iid,
        actor_user_id=user_id,
    )
    return iid


def _day(column: str, value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as e:
        raise ValueError(f"{column} {value!r} is not a date in YYYY-MM-DD form") from e


def _paise(rupees: str) -> int:
    """'125000' or '1,25,000.50' rupees to integer paise; anything else is refused, never guessed."""
    try:
        value = Decimal(rupees.replace(",", "").strip())
    except InvalidOperation as e:
        raise ValueError(f"amount_rupees {rupees!r} is not a number") from e
    if value != value.quantize(Decimal("0.01")):
        raise ValueError(f"amount_rupees {rupees!r} has more than 2 decimals")
    return int(value * 100)


def _reason(loc: tuple[int | str, ...], msg: str) -> str:
    msg = msg.removeprefix("Value error, ")
    column = {"name": "customer_name", "number": "invoice_number", "amount_paise": "amount_rupees"}
    return f"{column.get(str(loc[0]), loc[0])}: {msg}" if loc else msg


def _rows(csv_text: str) -> list[tuple[int, CustomerIn, InvoiceIn]]:
    if len(csv_text.encode()) > MAX_CSV_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, "The file is over 1 MB.")
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Missing columns: {', '.join(missing)}.")
    rows: list[tuple[int, CustomerIn, InvoiceIn]] = []
    errors: list[dict[str, str]] = []
    for n, r in enumerate(reader, start=2):  # row 1 is the header
        if len(rows) + len(errors) >= MAX_CSV_ROWS:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"The file has more than {MAX_CSV_ROWS} rows.")
        try:
            customer = CustomerIn.model_validate(
                {
                    "name": r["customer_name"] or "",
                    "email": r["email"] or "",
                    "phone": r["phone"] or "",
                    "segment": (r["segment"] or "sme").strip(),
                    "credit_terms_days": int(r["credit_terms_days"] or 30),
                }
            )
            invoice = InvoiceIn(
                number=(r["invoice_number"] or "").strip(),
                invoice_date=_day("invoice_date", r["invoice_date"] or ""),
                due_date=_day("due_date", r["due_date"] or ""),
                amount_paise=_paise(r["amount_rupees"] or ""),
            )
            rows.append((n, customer, invoice))
        except ValidationError as e:
            errors.append(
                {"field": f"row {n}", "reason": "; ".join(_reason(x["loc"], x["msg"]) for x in e.errors())}
            )
        except ValueError as e:
            errors.append({"field": f"row {n}", "reason": str(e)})
    if errors:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, f"{len(errors)} row(s) need fixing; nothing was saved.", errors
        )
    if not rows:
        raise AppError(ErrorCode.VALIDATION_ERROR, "The file has no rows.")
    return rows


def import_csv(session: Session, csv_text: str, user_id: str) -> Imported:
    """All or nothing: a bad row rolls the whole upload back. A known name gets the invoice; a new one is created."""
    rows = _rows(csv_text)
    found = session.execute(text("SELECT id::text AS id, name FROM customers")).mappings()
    known: dict[str, str] = {r["name"].lower(): r["id"] for r in found}
    created = 0
    for n, customer, invoice in rows:
        cid = known.get(customer.name.lower())
        if cid is None:
            cid = create_customer(session, customer, user_id)
            known[customer.name.lower()] = cid
            created += 1
        try:
            add_invoice(session, cid, invoice, user_id)
        except AppError as e:
            raise AppError(
                e.code,
                f"Row {n}: {e.message} Nothing was saved.",
                [{"field": f"row {n}", "reason": e.message}],
            ) from e
    return Imported(customers_created=created, invoices_added=len(rows))
