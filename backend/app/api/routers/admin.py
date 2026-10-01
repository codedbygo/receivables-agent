"""Admin: settings and kill switch, demo clock, reset, simulated bank credit, guardrail log (US-01-004, US-01-005,
US-01-008, US-01-009)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Admin, AppSettings, Reader, SessionDep, Today
from app.api.routers.records import receive
from app.services import ledger, overview, payments, runtime
from app.services.demo import reset_demo

router = APIRouter(prefix="/admin")


class ClockAdvance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(ge=1, le=60)


class ClockOut(BaseModel):
    demo_today: date


class SimulatedCredit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: uuid.UUID
    amount_paise: int = Field(gt=0)
    reference: str = Field(min_length=1, max_length=100)


class ResetOut(BaseModel):
    reset: bool
    demo_today: date


class GuardrailEventsPage(BaseModel):
    data: list[overview.GuardrailEventRow]


@router.get("/settings", response_model=runtime.RuntimeSettings)
def get_settings(session: SessionDep, _: Reader, s: AppSettings) -> runtime.RuntimeSettings:
    return runtime.read(session, s.llm_mode)


@router.patch("/settings", response_model=runtime.RuntimeSettings)
def update_settings(
    session: SessionDep, user: Admin, s: AppSettings, body: runtime.SettingsPatch
) -> runtime.RuntimeSettings:
    return runtime.update(session, body, s.llm_mode, user.id)


@router.post("/clock/advance", response_model=ClockOut)
def advance_clock(session: SessionDep, _: Admin, body: ClockAdvance) -> ClockOut:
    return ClockOut(demo_today=payments.advance_clock(session, body.days))


@router.post("/reset", response_model=ResetOut)
def reset(request: Request, _: Admin, s: AppSettings) -> ResetOut:
    reset_demo(request.app.state.engine, s)
    return ResetOut(reset=True, demo_today=date.fromisoformat(s.demo_today))


@router.post("/simulate/bank-credit", response_model=payments.Payment)
def simulate_credit(
    request: Request, session: SessionDep, _: Admin, today: Today, s: AppSettings, body: SimulatedCredit
) -> payments.Payment:
    """Signs server-side and goes through the webhook's own handler, so the demo exercises the real path."""
    name = ledger.get_customer(session, today, str(body.customer_id)).name
    credit = payments.BankCredit(
        event_id=f"sim-{uuid.uuid4()}",
        amount_paise=body.amount_paise,
        reference=body.reference,
        payer_name=name,
    )
    ts, sig, raw = payments.signed_credit(s.bank_webhook_secret, credit)
    return receive(request, s.bank_webhook_secret, ts, sig, raw)


@router.get("/guardrail-events", response_model=GuardrailEventsPage)
def guardrail_events(
    session: SessionDep,
    _: Admin,
    code: Annotated[str | None, Query(alias="filter[code]")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> GuardrailEventsPage:
    return GuardrailEventsPage(data=overview.guardrail_events(session, code, limit))
