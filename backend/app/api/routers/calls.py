"""Voice calls (HACK-003 F1): the console starts a call and, on a SIMULATED call, types what the customer says;
Twilio posts the customer's speech to the webhooks, which answer with TwiML. The signature is the credential."""

import uuid
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import Collector, Reader, SessionDep
from app.api.routers.records import read_capped
from app.channels.voice import signature_ok, twiml
from app.core.db import transaction
from app.core.errors import AppError, ErrorCode
from app.services import voice

router = APIRouter()
Id = Annotated[uuid.UUID, Path()]


class CallStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: uuid.UUID


class CustomerSays(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


class CallsPage(BaseModel):
    data: list[voice.Call]


@router.post("/calls", response_model=voice.Call)
def start_call(request: Request, session: SessionDep, user: Collector, body: CallStart) -> voice.Call:
    return voice.request(session, str(body.customer_id), user.id, request.app.state.voice)


@router.get("/calls", response_model=CallsPage)
def list_calls(
    session: SessionDep,
    _: Reader,
    customer_id: Annotated[uuid.UUID | None, Query(alias="filter[customer_id]")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CallsPage:
    return CallsPage(data=voice.list_calls(session, str(customer_id) if customer_id else None, limit))


@router.get("/calls/{id}", response_model=voice.Call)
def get_call(session: SessionDep, _: Reader, id: Id) -> voice.Call:
    return voice.get_call(session, str(id))


@router.post("/calls/{id}/turns", response_model=voice.Call)
def customer_says(
    request: Request, session: SessionDep, _: Collector, id: Id, body: CustomerSays
) -> voice.Call:
    """SIMULATED calls only: a collector types the customer's side. A real call's speech comes from Twilio."""
    if not voice.get_call(session, str(id)).simulated:
        raise AppError(ErrorCode.FORBIDDEN, "A real call takes the customer's speech from the provider only.")
    return voice.turn(session, str(id), body.text, request.app.state.orchestrator.gateway)


@router.post("/calls/{id}/end", response_model=voice.Call)
def end_call(session: SessionDep, _: Collector, id: Id) -> voice.Call:
    return voice.hang_up(session, str(id))


async def _signed_form(request: Request, signature: str) -> dict[str, str]:
    """The POSTed form, only when X-Twilio-Signature matches the public URL, the form and our auth token."""
    raw = await read_capped(request)
    params = dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True))
    s = request.app.state.settings
    url = s.voice_public_base_url.rstrip("/") + request.url.path
    if not (s.voice_public_base_url and signature_ok(s.twilio_auth_token, url, params, signature)):
        raise AppError(ErrorCode.SIGNATURE_INVALID, "Bad signature.")
    return params


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml")


@router.post("/webhooks/voice/{id}/turn")
async def voice_turn(
    request: Request, id: Id, signature: Annotated[str, Header(alias="X-Twilio-Signature")] = ""
) -> Response:
    params = await _signed_form(request, signature)
    return _xml(await run_in_threadpool(_turn_twiml, request, str(id), params))


def _turn_twiml(request: Request, call_id: str, params: dict[str, str]) -> str:
    with transaction(request.app.state.sessions) as s:
        call = voice.get_call(s, call_id)
        if call.provider != "twilio" or params.get("CallSid") != _provider_id(s, call_id):
            raise AppError(ErrorCode.NOT_FOUND, "Call not found.")
        speech = params.get("SpeechResult", "").strip()
        if speech and call.status == "in_progress":
            call = voice.turn(s, call_id, speech[:2000], request.app.state.orchestrator.gateway)
        last = next((t.text for t in reversed(call.turns) if t.speaker == "ai"), voice.SAFE_LINE)
        listen = call.status == "in_progress"
        url = request.app.state.settings.voice_public_base_url.rstrip("/") + request.url.path
        return twiml(last, url if listen else None)


def _provider_id(s: Session, call_id: str) -> str | None:
    return s.execute(
        text("SELECT provider_call_id FROM calls WHERE id = CAST(:k AS uuid)"), {"k": call_id}
    ).scalar()


@router.post("/webhooks/voice/{id}/status")
async def voice_status(
    request: Request, id: Id, signature: Annotated[str, Header(alias="X-Twilio-Signature")] = ""
) -> Response:
    params = await _signed_form(request, signature)

    def apply() -> None:
        with transaction(request.app.state.sessions) as s:
            if params.get("CallSid") == _provider_id(s, str(id)):
                voice.provider_status(s, str(id), params.get("CallStatus", ""))

    await run_in_threadpool(apply)
    return _xml('<?xml version="1.0" encoding="UTF-8"?><Response/>')
