"""Demo roles (US-01-007, engineer's decision 2026-09-30): the console picks admin, collector or viewer and
the API maps it to that role's seeded demo user. No passwords; the stack binds to localhost only."""

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

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
