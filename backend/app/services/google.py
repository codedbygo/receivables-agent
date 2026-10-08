"""The one company Google account (HACK-009, ADR-0018): the OAuth round trip, the encrypted refresh token, and an
authorised client the Gmail and Calendar services call. Google is reached with httpx only; no Google SDK."""

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
EXCHANGE_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
)
STATE_TTL_S = 600


class GoogleStatus(BaseModel):
    configured: bool
    connected: bool
    email: str | None
    connected_at: datetime | None
    email_provider: str


def http() -> httpx.Client:
    """Every call to Google goes through here; tests swap in an httpx.MockTransport."""
    return httpx.Client(timeout=10)


def _require_config(settings: Settings) -> None:
    if not (
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_token_key
        and settings.google_redirect_uri
    ):
        raise AppError(
            ErrorCode.GOOGLE_NOT_CONFIGURED,
            "Google is not set up: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_KEY and GOOGLE_REDIRECT_URI.",
        )


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), f"google:{body}".encode(), hashlib.sha256).hexdigest()[:32]


def _state(settings: Settings, user_id: str, now: float) -> str:
    body = f"{user_id}.{int(now) + STATE_TTL_S}.{secrets.token_hex(8)}"
    return f"{body}.{_sign(settings.session_secret, body)}"


def _user_from_state(settings: Settings, state: str, now: float) -> str:
    body, _, sig = state.rpartition(".")
    user_id, exp, _nonce = (body.split(".") + ["", "", ""])[:3]
    if not (exp.isdigit() and hmac.compare_digest(_sign(settings.session_secret, body), sig)) or now > int(
        exp
    ):
        raise AppError(
            ErrorCode.UNAUTHORIZED, "This Google sign-in link expired or is not valid; start again."
        )
    return user_id


def auth_url(settings: Settings, user_id: str, now: float | None = None) -> str:
    """Where an admin's browser goes to grant access. prompt=consent always returns a refresh token."""
    _require_config(settings)
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": _state(settings, user_id, time.time() if now is None else now),
    }
    return f"{AUTH_URL}?{urlencode(query)}"


LOGIN = "login"  # the state's subject for a sign-in; a mailbox connect carries the admin's user id instead


def is_login_state(state: str) -> bool:
    return state.startswith(f"{LOGIN}.")


def login_url(settings: Settings, now: float | None = None) -> str:
    """Sign in with Google (ADR-0019): only the verified email is asked for, on the same client and callback."""
    if not (settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri):
        raise AppError(ErrorCode.GOOGLE_NOT_CONFIGURED, "Sign in with Google is not set up here.")
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "prompt": "select_account",
        "state": _state(settings, LOGIN, time.time() if now is None else now),
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def login_email(settings: Settings, code: str, state: str, now: float | None = None) -> str:
    """The callback of a sign-in: the email Google verified for this person."""
    if _user_from_state(settings, state, time.time() if now is None else now) != LOGIN:
        raise AppError(ErrorCode.UNAUTHORIZED, "This Google sign-in link is not valid; start again.")
    tokens = _post_token(
        settings,
        {"code": code, "grant_type": "authorization_code", "redirect_uri": settings.google_redirect_uri},
    )
    try:
        with http() as c:
            info = c.get(USERINFO_URL, headers={"Authorization": f"Bearer {tokens.get('access_token', '')}"})
    except httpx.HTTPError as e:
        raise AppError(ErrorCode.GOOGLE_UPSTREAM, "Google did not answer; try again.") from e
    body = info.json() if info.status_code == 200 else {}
    if not body.get("email") or body.get("email_verified") is not True:
        raise AppError(ErrorCode.UNAUTHORIZED, "Google did not confirm a verified email for this account.")
    return str(body["email"])


def _fernet(settings: Settings) -> Fernet:
    try:
        return Fernet(settings.google_token_key.encode())
    except ValueError as e:
        raise AppError(ErrorCode.GOOGLE_NOT_CONFIGURED, "GOOGLE_TOKEN_KEY is not a valid Fernet key.") from e


def _post_token(settings: Settings, data: dict[str, str]) -> dict[str, Any]:
    try:
        with http() as c:
            r = c.post(
                EXCHANGE_URL,
                data={
                    **data,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                },
            )
    except httpx.HTTPError as e:
        raise AppError(ErrorCode.GOOGLE_UPSTREAM, "Google did not answer; try again.") from e
    if r.status_code != 200:
        code = ErrorCode.GOOGLE_NOT_CONNECTED if r.status_code in (400, 401) else ErrorCode.GOOGLE_UPSTREAM
        raise AppError(code, "Google refused the sign-in; connect Google again from the Admin page.")
    body: dict[str, Any] = r.json()
    return body


def complete(session: Session, settings: Settings, code: str, state: str, now: float | None = None) -> str:
    """The callback: check the state, swap the code for tokens, store the refresh token encrypted."""
    _require_config(settings)
    user_id = _user_from_state(settings, state, time.time() if now is None else now)
    tokens = _post_token(
        settings,
        {"code": code, "grant_type": "authorization_code", "redirect_uri": settings.google_redirect_uri},
    )
    refresh = tokens.get("refresh_token")
    granted = set(str(tokens.get("scope", "")).split())
    missing = [s for s in SCOPES[2:] if s not in granted]
    if not refresh or missing:
        raise AppError(
            ErrorCode.GOOGLE_NOT_CONNECTED,
            "Google did not grant every permission; connect again and tick them all.",
        )
    try:
        with http() as c:
            info = c.get(USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    except httpx.HTTPError as e:
        raise AppError(ErrorCode.GOOGLE_UPSTREAM, "Google did not answer; try again.") from e
    if info.status_code != 200 or not info.json().get("email"):
        raise AppError(ErrorCode.GOOGLE_UPSTREAM, "Google did not say which account was connected.")
    email = str(info.json()["email"])
    session.execute(
        text("""INSERT INTO google_account (id, email, refresh_token_enc, scopes, connected_by)
        VALUES (1, :e, :t, :s, CAST(:u AS uuid))
        ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, refresh_token_enc = EXCLUDED.refresh_token_enc,
          scopes = EXCLUDED.scopes, connected_by = EXCLUDED.connected_by, connected_at = now()"""),
        {
            "e": email,
            "t": _fernet(settings).encrypt(str(refresh).encode()).decode(),
            "s": " ".join(sorted(granted)),
            "u": user_id,
        },
    )
    return email


def status(session: Session, settings: Settings) -> GoogleStatus:
    row = session.execute(text("SELECT email, connected_at FROM google_account WHERE id = 1")).first()
    configured = bool(
        settings.google_client_id and settings.google_client_secret and settings.google_token_key
    )
    return GoogleStatus(
        configured=configured,
        connected=row is not None,
        email=row.email if row else None,
        connected_at=row.connected_at if row else None,
        email_provider=settings.email_provider,
    )


def disconnect(session: Session, settings: Settings) -> None:
    """Forget the account; tell Google to revoke the grant, best effort (the row goes either way)."""
    enc = session.execute(
        text("DELETE FROM google_account WHERE id = 1 RETURNING refresh_token_enc")
    ).scalar()
    if enc is None or not settings.google_token_key:
        return
    try:
        token = _fernet(settings).decrypt(enc.encode()).decode()
        with http() as c:
            c.post(REVOKE_URL, data={"token": token})
    except (InvalidToken, AppError, httpx.HTTPError):
        return  # the account is disconnected here; a stale grant can also be removed at myaccount.google.com


@dataclass
class Client:
    """An access token for the connected account and the account's address."""

    email: str
    token: str

    def call(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with http() as c:
                r = c.request(method, url, headers={"Authorization": f"Bearer {self.token}"}, **kwargs)
        except httpx.HTTPError as e:
            raise AppError(ErrorCode.GOOGLE_UPSTREAM, "Google did not answer; try again.") from e
        if r.status_code in (404, 410) and method == "DELETE":
            return {}  # already gone: the outcome the caller wanted
        if r.status_code >= 400:
            raise AppError(
                ErrorCode.GOOGLE_UPSTREAM, f"Google answered {r.status_code} to {method} {url.split('?')[0]}."
            )
        body: dict[str, Any] = r.json() if r.content else {}
        return body


def client(session: Session, settings: Settings) -> Client:
    """A fresh access token from the stored refresh token. ponytail: one token request per job or send; cache it
    in the process if Google ever rate-limits the refresh."""
    _require_config(settings)
    row = session.execute(text("SELECT email, refresh_token_enc FROM google_account WHERE id = 1")).first()
    if row is None:
        raise AppError(ErrorCode.GOOGLE_NOT_CONNECTED, "Connect Google from the Admin page first.")
    try:
        refresh = _fernet(settings).decrypt(row.refresh_token_enc.encode()).decode()
    except InvalidToken as e:
        raise AppError(
            ErrorCode.GOOGLE_NOT_CONNECTED, "The stored Google sign-in cannot be read; connect again."
        ) from e
    tokens = _post_token(settings, {"refresh_token": refresh, "grant_type": "refresh_token"})
    return Client(email=row.email, token=str(tokens["access_token"]))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")
