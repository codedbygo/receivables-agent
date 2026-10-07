"""Distributor and invoice management (HACK-007): collectors create, edit and upload; only an admin deletes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Admin, Collector, SessionDep, Today
from app.services import directory, ledger

router = APIRouter()
Id = Annotated[uuid.UUID, Path()]


class CsvIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: Annotated[str, Field(min_length=1, max_length=directory.MAX_CSV_BYTES)]


@router.post("/customers", response_model=ledger.Customer, status_code=201)
def create_customer(
    session: SessionDep, user: Collector, today: Today, body: directory.CustomerIn
) -> ledger.Customer:
    return ledger.get_customer(session, today, directory.create_customer(session, body, user.id))


@router.post("/customers/import", response_model=directory.Imported, status_code=201)
def import_customers(session: SessionDep, user: Collector, body: CsvIn) -> directory.Imported:
    return directory.import_csv(session, body.csv, user.id)


@router.patch("/customers/{id}", response_model=ledger.Customer)
def update_customer(
    session: SessionDep, user: Collector, today: Today, id: Id, body: directory.CustomerPatch
) -> ledger.Customer:
    directory.update_customer(session, str(id), body, user.id)
    return ledger.get_customer(session, today, str(id))


@router.delete("/customers/{id}", response_model=directory.Deleted)
def delete_customer(session: SessionDep, _: Admin, id: Id) -> directory.Deleted:
    return directory.delete_customer(session, str(id))


@router.post("/customers/{id}/invoices", response_model=ledger.Invoice, status_code=201)
def add_invoice(
    session: SessionDep, user: Collector, today: Today, id: Id, body: directory.InvoiceIn
) -> ledger.Invoice:
    directory.add_invoice(session, str(id), body, user.id)
    # ponytail: reads the customer's first 100 invoices, the same cap as the invoices page; a direct lookup if
    # one customer ever holds more
    return next(i for i in ledger.customer_invoices(session, today, str(id)) if i.number == body.number)
