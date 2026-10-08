"""Sign in and out as a person (HACK-011, ADR-0019), and the admin's list of people."""

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Path, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Admin, AppSettings, Reader, SessionDep
from app.core.db import transaction
from app.core.errors import AppError
from app.services import auth, google
from app.services.auth import SESSION_COOKIE, SESSION_HOURS, Person, Role, User

router = APIRouter(tags=["auth"])
Id = Annotated[uuid.UUID, Path()]
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL)
    password: str = Field(min_length=1, max_length=200)


class NewPerson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL)
    display_name: str = Field(min_length=1, max_length=100)
    role: Role
    password: str | None = Field(default=None, min_length=10, max_length=200)  # none: Google only


class PersonChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


class PeoplePage(BaseModel):
    data: list[Person]


def set_session_cookie(response: Response, raw: str) -> None:
    """HttpOnly so a script cannot read it; SameSite=Lax so another site cannot post with it; /api only."""
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=SESSION_HOURS * 3600,
        path="/api",
        httponly=True,
        secure=True,
        samesite="lax",
    )


@router.post("/auth/login", response_model=User)
def login(request: Request, response: Response, s: AppSettings, body: Credentials) -> User:
    # Its own transaction: a wrong password's count must be committed, and raising inside one rolls it back.
    with transaction(request.app.state.sessions) as session:
        found = auth.password_login(session, s, body.email, body.password)
        raw = auth.start_session(session, found.id) if isinstance(found, User) else ""
    if isinstance(found, AppError):
        raise found
    set_session_cookie(response, raw)
    return found


@router.post("/auth/logout", status_code=204)
def logout(request: Request, session: SessionDep) -> Response:
    auth.end_session(session, request.cookies.get(SESSION_COOKIE, ""))
    out = Response(status_code=204)
    out.delete_cookie(SESSION_COOKIE, path="/api", httponly=True, secure=True, samesite="lax")
    return out


@router.get("/auth/me", response_model=User)
def me(user: Reader) -> User:
    return user


@router.get("/auth/google")
def google_sign_in(s: AppSettings) -> RedirectResponse:
    """A plain link from the sign-in page: off to Google, back through /google/callback."""
    try:
        return RedirectResponse(google.login_url(s), status_code=303)
    except AppError as e:
        return RedirectResponse(f"/?signin_error={quote(e.message)}", status_code=303)


def google_callback(request: Request, s: AppSettings, code: str, state: str) -> RedirectResponse:
    """The sign-in half of /google/callback: a verified email that matches an active person gets a session."""
    try:
        email = google.login_email(s, code, state)
        with transaction(request.app.state.sessions) as session:
            raw = auth.start_session(session, auth.google_login(session, s, email).id)
    except AppError as e:
        return RedirectResponse(f"/?signin_error={quote(e.message)}", status_code=303)
    out = RedirectResponse("/#/", status_code=303)
    set_session_cookie(out, raw)
    return out


@router.get("/users", response_model=PeoplePage)
def people(session: SessionDep, _: Admin) -> PeoplePage:
    return PeoplePage(data=auth.people(session))


@router.post("/users", response_model=Person, status_code=201)
def add_person(session: SessionDep, _: Admin, body: NewPerson) -> Person:
    return auth.add_person(session, body.email, body.display_name, body.role, body.password)


@router.patch("/users/{id}", response_model=Person)
def change_person(session: SessionDep, user: Admin, id: Id, body: PersonChange) -> Person:
    return auth.update_person(session, user, str(id), body.role, body.active, body.password)
