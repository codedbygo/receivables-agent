"""Request-scoped dependencies: one session per request, the demo date, the signed-in user, role checks."""

from collections.abc import Callable, Iterator
from datetime import date
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.agent.orchestrator import Orchestrator
from app.core.clock import today
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services.auth import Role, User, demo_user, role_for_token

ROLE_HEADER = "X-Demo-Role"


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session, session.begin():
        yield session


def get_today(session: Annotated[Session, Depends(get_session)]) -> date:
    return today(session)


def current_user(request: Request, session: Annotated[Session, Depends(get_session)]) -> User:
    """The demo user for the caller's role; 401 without one (AC-US-01-007-3). The role is read from the access
    code in the Authorization header; the role header counts only when DEMO_OPEN_ROLES is on (laptop)."""
    settings: Settings = request.app.state.settings
    if settings.demo_open_roles:
        role: str | None = request.headers.get(ROLE_HEADER, "")
    else:
        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        role = role_for_token(settings, bearer)
    user = demo_user(session, role) if role else None
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "Sign in to continue.")
    return user


def require(*roles: Role) -> Callable[..., User]:
    """Role matrix check (LLD 8.1). Viewers read; collectors act on customers; admins run the system."""

    def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise AppError(ErrorCode.FORBIDDEN, "Your role cannot do this.")
        return user

    return check


Reader = Annotated[User, Depends(require("viewer", "collector", "admin"))]
Collector = Annotated[User, Depends(require("collector", "admin"))]
Admin = Annotated[User, Depends(require("admin"))]
SessionDep = Annotated[Session, Depends(get_session)]
Today = Annotated[date, Depends(get_today)]


def get_orchestrator(request: Request) -> Orchestrator:
    orch: Orchestrator = request.app.state.orchestrator
    return orch


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


Orch = Annotated[Orchestrator, Depends(get_orchestrator)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
