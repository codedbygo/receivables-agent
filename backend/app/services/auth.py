"""Roles (US-01-007): the API maps a role to that role's seeded demo user. The role comes from an access
code per role (hosted demo) or, with DEMO_OPEN_ROLES on a laptop, from the console's role header."""

import hmac
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings

Role = Literal["admin", "collector", "viewer"]
ROLES: tuple[Role, ...] = ("admin", "collector", "viewer")


class User(BaseModel):
    id: str
    email: str
    display_name: str
    role: Role


def demo_user(session: Session, role: str) -> User | None:
    if role not in ROLES:
        return None
    row = session.execute(
        text("""SELECT id::text, email, display_name, role FROM users WHERE role = :r
        ORDER BY email LIMIT 1"""),
        {"r": role},
    ).first()
    return User(id=row.id, email=row.email, display_name=row.display_name, role=row.role) if row else None


LOCAL_HOSTS = {"localhost", "127.0.0.1", "api", "testserver"}


def role_for_token(settings: Settings, bearer: str) -> Role | None:
    """The role whose access code this is; an unset code never matches."""
    found: Role | None = None
    codes: tuple[tuple[Role, str], ...] = (
        ("admin", settings.admin_token),
        ("collector", settings.collector_token),
        ("viewer", settings.viewer_token),
    )
    for role, code in codes:
        if code and bearer and hmac.compare_digest(bearer.encode(), code.encode()):
            found = role  # no early return: every code is compared
    return found


def check_auth_config(settings: Settings) -> None:
    """Refuse to start with an open door: header roles on a public host, or no way to sign in at all."""
    public = [h for h in settings.allowed_hosts.split(",") if h and h not in LOCAL_HOSTS]
    if settings.demo_open_roles and public:
        raise RuntimeError(
            f"DEMO_OPEN_ROLES is on but ALLOWED_HOSTS has public hosts {public}; set the access codes"
        )
    if not settings.demo_open_roles and not (
        settings.admin_token or settings.collector_token or settings.viewer_token
    ):
        raise RuntimeError(
            "No way to sign in: set ADMIN_TOKEN (and COLLECTOR_TOKEN, VIEWER_TOKEN) or DEMO_OPEN_ROLES"
        )
