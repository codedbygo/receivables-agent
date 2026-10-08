"""Connect the company Google account and sync with it (HACK-009, ADR-0018)."""

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.deps import Admin, AppSettings, Collector, Orch, Reader, SessionDep
from app.api.routers.auth import google_callback
from app.core.db import transaction
from app.core.errors import AppError, ErrorCode
from app.services import google, google_calendar, inbox, overview
from app.services.google import is_login_state

router = APIRouter(prefix="/google", tags=["google"])


class ConnectOut(BaseModel):
    url: str


class SyncOut(BaseModel):
    calendar: google_calendar.CalendarSync
    replies_found: int


class InboxPage(BaseModel):
    data: list[inbox.Inbound]


Id = Annotated[uuid.UUID, Path()]


@router.get("/status", response_model=google.GoogleStatus)
def status(session: SessionDep, _: Reader, s: AppSettings) -> google.GoogleStatus:
    return google.status(session, s)


@router.post("/connect", response_model=ConnectOut)
def connect(_session: SessionDep, user: Admin, s: AppSettings) -> ConnectOut:
    return ConnectOut(url=google.auth_url(s, user.id))


@router.get("/callback")
def callback(
    request: Request,
    s: AppSettings,
    state: Annotated[str, Query(max_length=200)] = "",
    code: Annotated[str, Query(max_length=2000)] = "",
    error: Annotated[str, Query(max_length=200)] = "",
) -> RedirectResponse:
    """Public: Google sends the browser here, for a sign-in or for an admin connecting the mailbox. The signed
    state is the credential, not a session, and says which of the two it is."""
    if is_login_state(state):
        if error or not code:
            return RedirectResponse(
                f"/?signin_error={quote('Google sign-in was cancelled.')}", status_code=303
            )
        return google_callback(request, s, code, state)
    try:
        if error or not code:
            raise AppError(ErrorCode.GOOGLE_NOT_CONNECTED, "Google sign-in was cancelled.")
        with transaction(request.app.state.sessions) as session:
            google.complete(session, s, code, state)
    except AppError as e:
        return RedirectResponse(f"/?google_error={quote(e.message)}#/admin", status_code=303)
    return RedirectResponse("/?google=connected#/admin", status_code=303)


@router.post("/disconnect", response_model=google.GoogleStatus)
def disconnect(session: SessionDep, _: Admin, s: AppSettings) -> google.GoogleStatus:
    google.disconnect(session, s)
    return google.status(session, s)


@router.post("/sync", response_model=SyncOut)
def sync(request: Request, _: Collector, s: AppSettings) -> SyncOut:
    """What the 5-minute job does, on demand: read new replies, then bring the calendar up to date."""
    engine = request.app.state.engine
    found = inbox.poll(engine, s) if s.email_provider == "gmail" else 0
    return SyncOut(calendar=google_calendar.sync(engine, s), replies_found=found)


@router.get("/inbox", response_model=InboxPage)
def incoming(session: SessionDep, _: Reader) -> InboxPage:
    return InboxPage(data=inbox.pending(session))


@router.post("/inbox/{id}/accept", response_model=overview.ReplyRow)
def accept(user: Collector, orch: Orch, id: Id) -> overview.ReplyRow:
    return inbox.accept(orch, str(id), user.id)


@router.post("/inbox/{id}/dismiss", response_model=inbox.Inbound)
def dismiss(session: SessionDep, user: Collector, id: Id) -> inbox.Inbound:
    return inbox.dismiss(session, str(id), user.id)
