"""Customers, invoices and priorities (US-00-001, US-00-002, US-00-026). Role checks arrive with US-01-007."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_today
from app.services import ledger
from app.services.priority import Factor, Priority, Reason, priorities, top

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
Today = Annotated[date, Depends(get_today)]
CustomerId = Annotated[uuid.UUID, Path()]
Limit = Annotated[int, Query(ge=1, le=100)]


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class PriorityOut(BaseModel):
    customer_id: str
    customer_name: str
    score: int
    band: Literal["HIGH", "MEDIUM", "LOW"]
    reasons: list[Reason]
    factors: list[Factor]


class CustomersPage(BaseModel):
    data: list[ledger.Customer]
    page: Page


class InvoicesPage(BaseModel):
    data: list[ledger.Invoice]
    page: Page


class PrioritiesPage(BaseModel):
    data: list[PriorityOut]
    page: Page


def _out(cid: str, name: str, p: Priority) -> PriorityOut:
    return PriorityOut(
        customer_id=cid, customer_name=name, score=p.score, band=p.band, reasons=p.reasons, factors=p.factors
    )


# ponytail: pages are one fetch up to limit (50 customers, <= 12 invoices each);
# cursors when data outgrows 100 rows
@router.get("/customers", response_model=CustomersPage)
def list_customers(session: SessionDep, today: Today, limit: Limit = 100) -> CustomersPage:
    return CustomersPage(data=ledger.list_customers(session, today, limit), page=Page())


@router.get("/customers/{id}", response_model=ledger.Customer)
def get_customer(session: SessionDep, today: Today, id: CustomerId) -> ledger.Customer:
    return ledger.get_customer(session, today, str(id))


@router.get("/customers/{id}/invoices", response_model=InvoicesPage)
def list_invoices(
    session: SessionDep,
    today: Today,
    id: CustomerId,
    status: Annotated[ledger.InvoiceStatus | None, Query(alias="filter[status]")] = None,
    limit: Limit = 100,
) -> InvoicesPage:
    data = ledger.customer_invoices(session, today, str(id), status, limit)
    return InvoicesPage(data=data, page=Page())


@router.get("/customers/{id}/priority", response_model=PriorityOut)
def get_priority(session: SessionDep, today: Today, id: CustomerId) -> PriorityOut:
    ledger.get_customer(session, today, str(id))
    cid, name, p = priorities(session, today, str(id))[0]
    return _out(cid, name, p)


@router.get("/priorities", response_model=PrioritiesPage)
def list_priorities(
    session: SessionDep, today: Today, limit: Annotated[int, Query(ge=1, le=100)] = 15
) -> PrioritiesPage:
    return PrioritiesPage(data=[_out(*t) for t in top(session, today, limit)], page=Page())
