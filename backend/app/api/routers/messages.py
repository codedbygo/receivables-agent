"""Approval queue, runs and replies (US-00-008 to US-00-012, US-01-001, US-01-006, US-01-016, US-03-001)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.agent import replies
from app.api.deps import Admin, AppSettings, Collector, Orch, Reader, SessionDep, Today
from app.core.db import transaction
from app.core.errors import AppError, ErrorCode
from app.services import approval, overview, runtime
from app.worker.jobs import enqueue
from app.worker.runner import send_handlers, tick

router = APIRouter()
Id = Annotated[uuid.UUID, Path()]
Limit = Annotated[int, Query(ge=1, le=100)]
IfMatch = Annotated[str, Header(alias="If-Match")]


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class MessagesPage(BaseModel):
    data: list[approval.Message]
    page: Page = Page()


class MessageEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    channel: Literal["email", "whatsapp"] | None = None


class Reject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class BatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    version: int = Field(ge=1)  # the version the collector saw; a newer draft is refused (STALE_DRAFT)


class BatchApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[BatchItem] = Field(min_length=1, max_length=50)


class RunStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_ids: list[uuid.UUID] = Field(default_factory=list, max_length=15)


class RunBatch(BaseModel):
    run_date: str
    job_id: int | None
    queued: bool
    run_ids: list[str]


class RunsPage(BaseModel):
    data: list[overview.Run]
    page: Page = Page()


class ReplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: uuid.UUID
    body: str = Field(min_length=1, max_length=5000)


def _version(if_match: str) -> int:
    try:
        return int(if_match.strip().removeprefix("W/").strip('"'))
    except ValueError as e:
        raise AppError(ErrorCode.VALIDATION_ERROR, "If-Match must be the message version.") from e


@router.get("/messages", response_model=MessagesPage)
def list_messages(
    session: SessionDep,
    _: Reader,
    status: Annotated[str | None, Query(alias="filter[status]")] = None,
    customer_id: Annotated[uuid.UUID | None, Query(alias="filter[customer_id]")] = None,
    limit: Limit = 100,
) -> MessagesPage:
    cid = str(customer_id) if customer_id else None
    return MessagesPage(data=approval.list_messages(session, status, cid, limit))


@router.post("/messages/approve-batch", response_model=MessagesPage)
def approve_batch(
    request: Request, settings: AppSettings, user: Collector, body: BatchApprove
) -> MessagesPage:
    """Assisted mode (US-01-016): each message passes the same checks as a single approval, at the version
    the collector saw. One stale draft refuses the whole batch (one transaction)."""
    with transaction(request.app.state.sessions) as session:
        if runtime.autonomy_mode(session) != "assisted":
            raise AppError(ErrorCode.FEATURE_DISABLED, "Batch approval needs Assisted mode.")
        data = [approval.approve(session, str(m.id), m.version, user.id) for m in body.messages]
    _send_inline(request, settings)
    return MessagesPage(data=[approval.get_message_now(request.app.state.sessions, str(m.id)) for m in data])


@router.get("/messages/{id}", response_model=approval.Message)
def get_message(session: SessionDep, _: Reader, id: Id) -> approval.Message:
    return approval.get_message(session, str(id))


@router.patch("/messages/{id}", response_model=approval.Message)
def edit_message(
    session: SessionDep, user: Collector, id: Id, body: MessageEdit, if_match: IfMatch
) -> approval.Message:
    return approval.edit(session, str(id), body.subject, body.body, _version(if_match), user.id, body.channel)


@router.post("/messages/{id}/approve", response_model=approval.Message)
def approve_message(
    request: Request, settings: AppSettings, user: Collector, id: Id, if_match: IfMatch
) -> approval.Message:
    # Its own transaction: the approval and its send job must be committed before an inline send claims it.
    with transaction(request.app.state.sessions) as session:
        approval.approve(session, str(id), _version(if_match), user.id)
    _send_inline(request, settings)
    return approval.get_message_now(request.app.state.sessions, str(id))


def _send_inline(request: Request, settings: AppSettings) -> None:
    """Serverless (ADR-0015): no worker runs between requests, so send the queued messages now."""
    if settings.send_inline:
        tick(request.app.state.engine, send_handlers(settings), budget_s=20)


@router.post("/messages/{id}/reject", response_model=approval.Message)
def reject_message(session: SessionDep, user: Collector, id: Id, body: Reject) -> approval.Message:
    return approval.reject(session, str(id), body.reason, user.id)


@router.post("/messages/{id}/resend", response_model=approval.Message)
def resend_message(session: SessionDep, user: Collector, id: Id) -> approval.Message:
    return approval.resend(session, str(id), user.id)


@router.post("/runs", response_model=RunBatch, status_code=202)
def start_run(session: SessionDep, _: Admin, today: Today, orch: Orch, body: RunStart) -> RunBatch:
    """No customers: queue today's daily run for the worker. Named customers: run them now, in this request,
    so the demo does not wait on the worker (trigger 'manual'; the same bounded loop)."""
    if not body.customer_ids:
        job = enqueue(session.connection(), "daily_run", str(today), {"run_date": str(today)})
        return RunBatch(run_date=str(today), job_id=job, queued=job is not None, run_ids=[])
    done = [orch.run_collections(str(c), "manual") for c in body.customer_ids]
    ids = [r.id for r in done if r is not None]
    if not ids:
        raise AppError(ErrorCode.VALIDATION_ERROR, "A run for this customer is already in progress.")
    return RunBatch(run_date=str(today), job_id=None, queued=False, run_ids=ids)


@router.get("/runs", response_model=RunsPage)
def list_runs(session: SessionDep, _: Admin, limit: Limit = 20) -> RunsPage:
    return RunsPage(data=overview.runs(session, limit=limit))


@router.get("/runs/{id}", response_model=overview.Run)
def get_run(session: SessionDep, _: Reader, id: Id) -> overview.Run:
    return overview.runs(session, run_id=str(id))[0]


@router.post("/replies", response_model=overview.ReplyRow, status_code=201)
def create_reply(_: Collector, orch: Orch, body: ReplyCreate) -> overview.ReplyRow:
    """Paste a customer's reply: stored, classified, acted on (Flow B). The reply is committed before the run
    reads it, so it uses the orchestrator's sessions rather than the request's."""
    with transaction(orch.sessions) as s:
        rid, _customer = replies.ingest(s, str(body.message_id), body.body)
    replies.understand(orch, rid)
    with orch.sessions() as s:
        return overview.get_reply(s, rid)


@router.get("/replies/{id}", response_model=overview.ReplyRow)
def get_reply(session: SessionDep, _: Reader, id: Id) -> overview.ReplyRow:
    return overview.get_reply(session, str(id))
