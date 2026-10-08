"""Dashboard, timeline, promises, disputes, escalations, payments and the bank webhook (US-00-003, US-00-004,
US-00-013 to US-00-020, US-01-004, US-01-007)."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import AppSettings, Collector, Reader, SessionDep, Today
from app.core.db import transaction
from app.core.errors import AppError, ErrorCode
from app.evaluation.harness import latest
from app.services import (
    callprep,
    collections,
    communication,
    disputes,
    executive,
    followups,
    memory,
    overview,
    paylink,
    payments,
    safety,
)

router = APIRouter()
Id = Annotated[uuid.UUID, Path()]
Limit = Annotated[int, Query(ge=1, le=100)]
CustomerFilter = Annotated[uuid.UUID | None, Query(alias="filter[customer_id]")]


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class TimelinePage(BaseModel):
    data: list[overview.TimelineEvent]
    next_action: str
    page: Page = Page()


class RunsPage(BaseModel):
    data: list[overview.Run]
    page: Page = Page()


class PromisesPage(BaseModel):
    data: list[overview.PromiseRow]
    page: Page = Page()


class PromiseCheck(BaseModel):
    promise: overview.PromiseRow
    matched_payment_ids: list[str]
    message: str


class DisputesPage(BaseModel):
    data: list[overview.DisputeRow]
    page: Page = Page()


class EscalationsPage(BaseModel):
    data: list[overview.EscalationRow]
    page: Page = Page()


class PaymentsPage(BaseModel):
    data: list[overview.PaymentRow]
    page: Page = Page()


class Resolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=500)


class PaymentMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: uuid.UUID


class Ageing(BaseModel):
    d0_30_paise: int
    d31_60_paise: int
    d61_90_paise: int
    d90_plus_paise: int


class Dashboard(BaseModel):
    """Every figure is computed by overview.dashboard from the ledger. Money is typed int here because
    Postgres returns SUM(bigint) as numeric, which would otherwise serialise as a string."""

    today: date
    total_outstanding_paise: int
    total_overdue_paise: int
    customers_overdue: int
    todays_promises: int
    missed_promises: int
    open_disputes: int
    pending_approvals: int
    high_risk_customers: int
    open_escalations: int
    ageing: Ageing
    attention: dict[str, list[dict[str, Any]]]


class EvalReport(BaseModel):
    """The last `make eval` output (evals/report.json), shown on the Evaluation page."""

    model_config = ConfigDict(extra="allow")
    generated_at: str
    mode: str
    command: str


@router.get("/evals/latest", response_model=EvalReport)
def latest_eval(_: Reader) -> EvalReport:
    report = latest()
    if report is None:
        raise AppError(ErrorCode.NOT_FOUND, "No evaluation yet. Run make eval.")
    return EvalReport(**report)


def _cid(c: uuid.UUID | None) -> str | None:
    return str(c) if c else None


@router.get("/dashboard", response_model=Dashboard)
def dashboard(session: SessionDep, _: Reader, today: Today) -> dict[str, Any]:
    return overview.dashboard(session, today)


@router.get("/executive", response_model=executive.Executive)
def executive_dashboard(session: SessionDep, _: Reader, today: Today) -> executive.Executive:
    """CFO view (HACK-003 F8): every figure from the ledger, with its definition."""
    return executive.executive(session, today)


@router.get("/safety", response_model=safety.Safety)
def safety_center(session: SessionDep, _: Reader) -> safety.Safety:
    """AI Safety Center: counts of real guardrail, approval and send events."""
    return safety.safety(session)


@router.get("/customers/{id}/timeline", response_model=TimelinePage)
def timeline(
    session: SessionDep, _: Reader, today: Today, id: Id, limit: Annotated[int, Query(ge=1, le=500)] = 200
) -> TimelinePage:
    cid = str(id)
    return TimelinePage(
        data=overview.timeline(session, cid, limit), next_action=overview.next_action(session, cid, today)
    )


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=2000)


class ContactPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferred_channel: Literal["email", "whatsapp", "sms", "voice"] | None = None
    consent: dict[Literal["whatsapp", "sms", "voice"], bool] = Field(default_factory=dict)


@router.get("/customers/{id}/memory", response_model=memory.Memory)
def customer_memory(session: SessionDep, _: Reader, id: Id) -> memory.Memory:
    """HACK-003 F3: interaction history from rows, plus internal notes (signed-in roles only)."""
    return memory.full(session, str(id))


@router.post("/customers/{id}/notes", response_model=memory.Note)
def add_note(session: SessionDep, user: Collector, id: Id, body: NoteIn) -> memory.Note:
    return memory.add_note(session, str(id), body.body, user.id)


@router.get("/customers/{id}/channels", response_model=communication.ChannelPlan)
def channel_plan(session: SessionDep, _: Reader, today: Today, id: Id) -> communication.ChannelPlan:
    """HACK-003 F2: preferred, last and next channel, with the factors behind the recommendation."""
    return communication.plan(session, str(id), today)


@router.put("/customers/{id}/contact-preferences", response_model=communication.ChannelPlan)
def set_contact_preferences(
    session: SessionDep, user: Collector, today: Today, id: Id, body: ContactPreferences
) -> communication.ChannelPlan:
    consent = {str(k): v for k, v in body.consent.items()}
    communication.set_preferences(session, str(id), body.preferred_channel, consent, user.id)
    return communication.plan(session, str(id), today)


@router.get("/customers/{id}/runs", response_model=RunsPage)
def customer_runs(session: SessionDep, _: Reader, id: Id, limit: Limit = 20) -> RunsPage:
    return RunsPage(data=overview.runs(session, customer_id=str(id), limit=limit))


@router.get("/promises", response_model=PromisesPage)
def list_promises(
    session: SessionDep,
    _: Reader,
    today: Today,
    customer_id: CustomerFilter = None,
    status: Annotated[str | None, Query(alias="filter[status]")] = None,
    due_today: Annotated[bool, Query(alias="filter[due]")] = False,
    limit: Limit = 100,
) -> PromisesPage:
    due = today if due_today else None
    return PromisesPage(data=overview.list_promises(session, status, _cid(customer_id), due, limit))


@router.post("/promises/{id}/check-payment", response_model=PromiseCheck)
def check_payment(session: SessionDep, _: Collector, id: Id) -> PromiseCheck:
    customer_id, paid_ids, message = payments.check_promise(session, str(id))
    promise = next(p for p in overview.list_promises(session, None, customer_id, None) if p.id == str(id))
    return PromiseCheck(promise=promise, matched_payment_ids=paid_ids, message=message)


@router.get("/disputes", response_model=DisputesPage)
def list_disputes(
    session: SessionDep,
    _: Reader,
    customer_id: CustomerFilter = None,
    status: Annotated[str | None, Query(alias="filter[status]")] = None,
    limit: Limit = 100,
) -> DisputesPage:
    return DisputesPage(data=overview.list_disputes(session, status, _cid(customer_id), limit))


class DisputeMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: Literal["assigned", "investigating"]
    team: Literal["billing", "operations", "sales", "legal_contracts", "collections"] | None = None
    note: str | None = Field(None, max_length=500)


@router.post("/disputes/{id}/transition", response_model=overview.DisputeRow)
def move_dispute(session: SessionDep, user: Collector, id: Id, body: DisputeMove) -> overview.DisputeRow:
    """Assign, reassign or start investigating (HACK-003 F7). Resolving is /resolve, which needs a note."""
    cid = disputes.transition(session, str(id), body.to, user.id, body.note, body.team)
    return next(d for d in overview.list_disputes(session, None, cid) if d.id == str(id))


@router.post("/disputes/{id}/resolve", response_model=collections.DisputeOut)
def resolve_dispute(session: SessionDep, user: Collector, id: Id, body: Resolve) -> collections.DisputeOut:
    return collections.resolve_dispute(session, str(id), body.note, user.id)


class FollowUpsPage(BaseModel):
    data: list[followups.FollowUp]
    page: Page = Page()


class FollowUpClose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["done", "cancelled"]
    note: str = Field(min_length=1, max_length=500)


@router.get("/follow-ups", response_model=FollowUpsPage)
def list_followups(
    session: SessionDep,
    _: Reader,
    customer_id: CustomerFilter = None,
    status: Annotated[Literal["open", "done", "cancelled"] | None, Query(alias="filter[status]")] = None,
    limit: Limit = 100,
) -> FollowUpsPage:
    """Missed and partly kept promises waiting for a collector (HACK-003 F5)."""
    return FollowUpsPage(data=followups.list_followups(session, status, _cid(customer_id), limit))


@router.post("/follow-ups/{id}/close", response_model=followups.FollowUp)
def close_followup(session: SessionDep, user: Collector, id: Id, body: FollowUpClose) -> followups.FollowUp:
    return followups.close(session, str(id), body.status, body.note, user.id)


@router.get("/escalations", response_model=EscalationsPage)
def list_escalations(
    session: SessionDep,
    _: Reader,
    customer_id: CustomerFilter = None,
    status: Annotated[str | None, Query(alias="filter[status]")] = None,
    limit: Limit = 100,
) -> EscalationsPage:
    return EscalationsPage(data=overview.list_escalations(session, status, _cid(customer_id), limit))


@router.post("/escalations/{id}/resolve", response_model=collections.EscalationOut)
def resolve_escalation(
    session: SessionDep, user: Collector, id: Id, body: Resolve
) -> collections.EscalationOut:
    return collections.resolve_escalation(session, str(id), body.note, user.id)


@router.get("/payments", response_model=PaymentsPage)
def list_payments(
    session: SessionDep,
    _: Reader,
    customer_id: CustomerFilter = None,
    status: Annotated[str | None, Query(alias="filter[match_status]")] = None,
    limit: Limit = 100,
) -> PaymentsPage:
    return PaymentsPage(data=overview.list_payments(session, status, _cid(customer_id), limit))


@router.post("/payments/{id}/match", response_model=payments.Payment)
def match_payment(session: SessionDep, _: Collector, id: Id, body: PaymentMatch) -> payments.Payment:
    return payments.match_payment(session, str(id), str(body.customer_id))


MAX_WEBHOOK_BYTES = 64 * 1024


async def read_capped(request: Request) -> bytes:
    """The request body, read chunk by chunk; stops as soon as it passes the cap (a chunked request has no
    Content-Length to check up front)."""
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Invalid Content-Length.") from None
    if declared > MAX_WEBHOOK_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Body too large.")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_WEBHOOK_BYTES:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Body too large.")
    return bytes(body)


@router.post("/webhooks/bank", response_model=payments.Payment)
async def bank_webhook(
    request: Request,
    timestamp: Annotated[str, Header(alias="X-Bank-Timestamp")],
    signature: Annotated[str, Header(alias="X-Bank-Signature")],
) -> payments.Payment:
    """Signed simulated bank feed (REQ-116). No role: the HMAC is the credential."""
    raw = await read_capped(request)
    secret = request.app.state.settings.bank_webhook_secret
    return await run_in_threadpool(receive, request, secret, timestamp, signature, raw)


def receive(request: Request, secret: str, timestamp: str, signature: str, raw: bytes) -> payments.Payment:
    """Shared by the webhook and the admin 'simulate credit' button (HLD Flow C)."""
    payments.verify_signature(secret, timestamp, signature, raw)
    credit = payments.BankCredit.model_validate_json(raw)
    with transaction(request.app.state.sessions) as s:
        return payments.receive_credit(s, credit)


@router.get("/customers/{id}/call-prep", response_model=callprep.CallPrep)
def call_prep(session: SessionDep, _: Collector, id: Id) -> callprep.CallPrep:
    return callprep.prepare(session, str(id))


InvoiceNumber = Annotated[str, Path(pattern=r"^INV-\d+$")]


@router.post("/invoices/{number}/pay-link", response_model=paylink.LinkOut)
def create_pay_link(
    session: SessionDep, _: Collector, s: AppSettings, number: InvoiceNumber
) -> paylink.LinkOut:
    return paylink.create(session, s.session_secret, number)


PayToken = Annotated[str, Path(max_length=80)]


@router.get("/pay/{token}", response_model=paylink.PayLink)
def get_pay_link(session: SessionDep, s: AppSettings, token: PayToken) -> paylink.PayLink:
    """Public: the signed token is the credential (a customer opens it from an email)."""
    return paylink.read(session, s.session_secret, token)


@router.post("/pay/{token}", response_model=payments.Payment)
def pay_link(session: SessionDep, s: AppSettings, token: PayToken) -> payments.Payment:
    return paylink.pay(session, s.session_secret, token)
