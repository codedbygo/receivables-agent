"""Who is calling (ADR-0019): a person signed in with an email and password or with Google, held by a session
row whose id is the SHA-256 of the cookie. ADMIN_TOKEN still signs scripts in as an admin, and DEMO_OPEN_ROLES
lets a laptop (and the tests) pick a role with a header; neither is a way into the console."""

import hashlib
import hmac
import os
import secrets
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

Role = Literal["admin", "collector", "viewer"]
ROLES: tuple[Role, ...] = ("admin", "collector", "viewer")

SESSION_COOKIE = "ca_session"
SESSION_HOURS = 12
MAX_FAILED = 5
LOCK_MINUTES = 15
UNUSABLE_HASH = "!"  # a Google-only person: no password matches it

DEMO_USERS = [
    ("admin@example.in", "Asha (Admin)", "admin"),
    ("collector@example.in", "Priya (Collector)", "collector"),
    ("viewer@example.in", "Vikram (Viewer)", "viewer"),
]
DEMO_PASSWORD = "demo-password"  # noqa: S105  demo accounts only, printed in the README; refused when hosted
WRONG = "Email or password is wrong."


class User(BaseModel):
    id: str
    email: str
    display_name: str
    role: Role


class Person(User):
    """A user as the admin's People list shows them."""

    active: bool
    has_password: bool
    locked: bool


def hash_password(password: str, salt: bytes | None = None) -> str:
    """scrypt from the standard library (LLD 11): 'scrypt$<salt hex>$<hash hex>'."""
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    kind, _, rest = stored.partition("$")
    salt_hex, _, digest_hex = rest.partition("$")
    try:
        salt, want = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    except ValueError:
        return False
    if kind != "scrypt" or not salt or not want:
        return False
    got = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(got, want)


# An unknown email still costs one scrypt, so the time taken does not say which emails exist.
_DUMMY_HASH = hash_password("not a password", salt=bytes(16))


def demo_user(session: Session, role: str) -> User | None:
    if role not in ROLES:
        return None
    row = session.execute(
        text("""SELECT id::text, email, display_name, role FROM users WHERE role = :r AND active
        ORDER BY email LIMIT 1"""),
        {"r": role},
    ).first()
    return User(id=row.id, email=row.email, display_name=row.display_name, role=row.role) if row else None


def refused_here(settings: Settings, email: str) -> bool:
    """The seeded demo accounts have a published password: they sign in on a laptop only."""
    return not settings.demo_open_roles and email.strip().lower() in {e for e, _, _ in DEMO_USERS}


def _bootstrap(session: Session, settings: Settings, email: str, password: str | None) -> None:
    """The first admin of a hosted deployment, named by BOOTSTRAP_ADMIN_EMAIL: created the first time that email
    signs in with Google, or with BOOTSTRAP_ADMIN_PASSWORD. Never re-created or switched back on once it exists, so
    an admin who turns that person off stays in charge."""
    want = settings.bootstrap_admin_email.strip().lower()
    if not want or email.strip().lower() != want:
        return
    if password is not None and not (
        settings.bootstrap_admin_password
        and hmac.compare_digest(password.encode(), settings.bootstrap_admin_password.encode())
    ):
        return
    session.execute(
        text("""INSERT INTO users (email, display_name, role, password_hash)
        VALUES (:e, :n, 'admin', :h)
        ON CONFLICT DO NOTHING"""),
        {"e": want, "n": want.split("@")[0], "h": hash_password(password) if password else UNUSABLE_HASH},
    )


def password_login(session: Session, settings: Settings, email: str, password: str) -> User | AppError:
    """The person, or the error to show. The error is returned, not raised, so the caller commits the failed
    attempt count before answering (raising would roll it back)."""
    if not refused_here(settings, email):
        _bootstrap(session, settings, email, password)
    row = session.execute(
        text("""SELECT id::text, email, display_name, role, password_hash,
        COALESCE(locked_until > now(), false) AS locked
        FROM users WHERE lower(email) = lower(:e) AND active FOR UPDATE"""),
        {"e": email.strip()},
    ).first()
    if row is None or refused_here(settings, row.email):
        verify_password(password, _DUMMY_HASH)
        return AppError(ErrorCode.UNAUTHORIZED, WRONG)
    if row.locked:
        return AppError(
            ErrorCode.RATE_LIMITED, f"Too many wrong passwords. Try again in {LOCK_MINUTES} minutes."
        )
    if not verify_password(password, row.password_hash):
        session.execute(
            text("""UPDATE users SET failed_logins = failed_logins + 1,
            locked_until = CASE WHEN failed_logins + 1 >= :max THEN now() + make_interval(mins => :m) END
            WHERE id = CAST(:u AS uuid)"""),
            {"max": MAX_FAILED, "m": LOCK_MINUTES, "u": row.id},
        )
        return AppError(ErrorCode.UNAUTHORIZED, WRONG)
    session.execute(
        text("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = CAST(:u AS uuid)"),
        {"u": row.id},
    )
    return User(id=row.id, email=row.email, display_name=row.display_name, role=row.role)


def google_login(session: Session, settings: Settings, email: str) -> User:
    """A Google-verified email: the active person with that email, or 401."""
    if refused_here(settings, email):
        raise AppError(ErrorCode.UNAUTHORIZED, f"{email} has no access. Ask an admin to add you.")
    _bootstrap(session, settings, email, None)
    row = session.execute(
        text(
            """SELECT id::text, email, display_name, role FROM users WHERE lower(email) = lower(:e) AND active"""
        ),
        {"e": email.strip()},
    ).first()
    if row is None:
        raise AppError(ErrorCode.UNAUTHORIZED, f"{email} has no access. Ask an admin to add you.")
    return User(id=row.id, email=row.email, display_name=row.display_name, role=row.role)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def start_session(session: Session, user_id: str) -> str:
    """A new session; returns the cookie value, of which only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    session.execute(
        text("DELETE FROM sessions WHERE user_id = CAST(:u AS uuid) AND expires_at < now()"), {"u": user_id}
    )
    session.execute(
        text("""INSERT INTO sessions (id, user_id, expires_at)
        VALUES (:h, CAST(:u AS uuid), now() + make_interval(hours => :n))"""),
        {"h": _digest(raw), "u": user_id, "n": SESSION_HOURS},
    )
    return raw


def user_for_session(session: Session, raw: str) -> User | None:
    if not raw:
        return None
    row = session.execute(
        text("""SELECT u.id::text, u.email, u.display_name, u.role FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.id = :h AND s.expires_at > now() AND u.active"""),
        {"h": _digest(raw)},
    ).first()
    return User(id=row.id, email=row.email, display_name=row.display_name, role=row.role) if row else None


def end_session(session: Session, raw: str) -> None:
    session.execute(text("DELETE FROM sessions WHERE id = :h"), {"h": _digest(raw)})


PERSON = """SELECT id::text, email, display_name, role, active, password_hash <> '!' AS has_password,
    COALESCE(locked_until > now(), false) AS locked FROM users"""


def _person(row: object) -> Person:
    return Person.model_validate(row, from_attributes=True)


def people(session: Session) -> list[Person]:
    return [
        _person(r) for r in session.execute(text(PERSON + " ORDER BY active DESC, lower(email) LIMIT 500"))
    ]


def add_person(session: Session, email: str, display_name: str, role: Role, password: str | None) -> Person:
    new = session.execute(
        text("""INSERT INTO users (email, display_name, role, password_hash)
        VALUES (:e, :n, :r, :h) ON CONFLICT DO NOTHING RETURNING id::text"""),
        {
            "e": email.strip(),
            "n": display_name.strip(),
            "r": role,
            "h": hash_password(password) if password else UNUSABLE_HASH,
        },
    ).scalar()
    if new is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Someone already has that email.")
    return _person(session.execute(text(PERSON + " WHERE id = CAST(:u AS uuid)"), {"u": new}).one())


def update_person(
    session: Session,
    actor: User,
    person_id: str,
    role: Role | None,
    active: bool | None,
    password: str | None,
) -> Person:
    """Change a role, switch someone off or on, or set a new password. Switching off ends their sessions."""
    if person_id == actor.id and (active is False or (role is not None and role != "admin")):
        raise AppError(ErrorCode.VALIDATION_ERROR, "You cannot remove your own admin access.")
    found = session.execute(
        text("""UPDATE users SET role = COALESCE(:r, role), active = COALESCE(:a, active),
        password_hash = COALESCE(:h, password_hash),
        failed_logins = CASE WHEN :h IS NULL THEN failed_logins ELSE 0 END,
        locked_until = CASE WHEN :h IS NULL THEN locked_until END
        WHERE id = CAST(:u AS uuid) RETURNING id"""),
        {"r": role, "a": active, "h": hash_password(password) if password else None, "u": person_id},
    ).first()
    if found is None:
        raise AppError(ErrorCode.NOT_FOUND, "Person not found.")
    if active is False:
        session.execute(text("DELETE FROM sessions WHERE user_id = CAST(:u AS uuid)"), {"u": person_id})
    return _person(session.execute(text(PERSON + " WHERE id = CAST(:u AS uuid)"), {"u": person_id}).one())


LOCAL_HOSTS = {"localhost", "127.0.0.1", "api", "testserver"}


def is_admin_token(settings: Settings, bearer: str) -> bool:
    """ADMIN_TOKEN, for scripts (smoke run, MCP); an unset token never matches."""
    code = settings.admin_token
    return bool(code and bearer and hmac.compare_digest(bearer.encode(), code.encode()))


def check_auth_config(settings: Settings) -> None:
    """Refuse to start with an open door: header roles on a public host."""
    public = [h for h in settings.allowed_hosts.split(",") if h and h not in LOCAL_HOSTS]
    if settings.demo_open_roles and public:
        raise RuntimeError(
            f"DEMO_OPEN_ROLES is on but ALLOWED_HOSTS has public hosts {public}; people sign in with a password "
            "or Google there"
        )
