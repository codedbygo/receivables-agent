"""Customer payment portal (HACK-003 F6). Public routes: the token in the path is the only credential and resolves to
one customer. Collector routes create and revoke links. Request logs never carry the token (main.py)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import AppSettings, Collector, SessionDep
from app.services import portal

router = APIRouter()
Token = Annotated[str, Path(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]
Id = Annotated[uuid.UUID, Path()]


class PromiseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_paise: int = Field(gt=0)
    promised_date: date


class DisputeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_number: str = Field(pattern=r"^INV-\d+$")
    description: str = Field(min_length=1, max_length=portal.MAX_TEXT)


class HelpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=portal.MAX_TEXT)


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_number: str = Field(pattern=r"^INV-\d+$")


class Revoked(BaseModel):
    revoked: int


@router.post("/customers/{id}/portal-link", response_model=portal.LinkOut)
def create_link(session: SessionDep, user: Collector, id: Id) -> portal.LinkOut:
    """The token is shown once; only its hash is stored."""
    return portal.create_link(session, str(id), user.id)


@router.post("/customers/{id}/portal-links/revoke", response_model=Revoked)
def revoke_links(session: SessionDep, user: Collector, id: Id) -> Revoked:
    return Revoked(revoked=portal.revoke_links(session, str(id), user.id))


@router.get("/portal/{token}", response_model=portal.PortalView)
def view(session: SessionDep, token: Token) -> portal.PortalView:
    return portal.view(session, token)


@router.post("/portal/{token}/promise", response_model=portal.PortalAck)
def promise(session: SessionDep, token: Token, body: PromiseIn) -> portal.PortalAck:
    return portal.promise(session, token, body.amount_paise, body.promised_date)


@router.post("/portal/{token}/dispute", response_model=portal.PortalAck)
def dispute(session: SessionDep, token: Token, body: DisputeIn) -> portal.PortalAck:
    return portal.dispute(session, token, body.invoice_number, body.description)


@router.post("/portal/{token}/help", response_model=portal.PortalAck)
def help_request(session: SessionDep, token: Token, body: HelpIn) -> portal.PortalAck:
    return portal.help_request(session, token, body.message)


@router.post("/portal/{token}/pay", response_model=portal.PortalAck)
def pay(session: SessionDep, s: AppSettings, token: Token, body: PayIn) -> portal.PortalAck:
    """SIMULATED: no payment processor; the credit goes through the same ledger path as the bank feed."""
    return portal.pay(session, token, s.session_secret, body.invoice_number)
