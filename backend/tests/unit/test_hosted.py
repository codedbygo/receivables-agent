"""Hosted on Vercel + Neon (ADR-0015, ADR-0016): database URLs as Neon gives them, no connection pool in a
serverless function, and real SMTP that only ever mails the demo inbox."""

import smtplib
from email.message import EmailMessage

import pytest
from sqlalchemy.pool import NullPool

from app.api.main import create_app
from app.channels.email import EmailChannel, Outbound
from app.core.config import Settings
from app.core.db import make_engine

NEON = "u:p@ep-x.neon.tech/neondb?sslmode=require"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_a_neon_url_is_used_with_the_psycopg_driver_and_keeps_tls(scheme: str) -> None:
    assert Settings(database_url=f"{scheme}://{NEON}").database_url == f"postgresql+psycopg://{NEON}"


def test_a_serverless_function_holds_no_pooled_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")

    assert isinstance(make_engine(f"postgresql+psycopg://{NEON}").pool, NullPool)


def test_a_long_running_process_keeps_its_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)

    assert not isinstance(make_engine(f"postgresql+psycopg://{NEON}").pool, NullPool)


class RecordingSMTP:
    calls: list[tuple[str, object]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.calls.append(("connect", (host, port)))

    def __enter__(self) -> "RecordingSMTP":
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def starttls(self) -> None:
        self.calls.append(("starttls", None))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user))

    def send_message(self, m: EmailMessage) -> None:
        self.calls.append(("send", m))


def test_real_smtp_logs_in_over_tls_and_mails_only_the_demo_inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingSMTP.calls = []
    monkeypatch.setattr(smtplib, "SMTP", RecordingSMTP)
    channel = EmailChannel(
        "smtp.gmail.com",
        587,
        username="me@gmail.com",
        password="app-password",
        starttls=True,
        from_addr="me@gmail.com",
        redirect_to="inbox@gmail.com",
    )

    channel.send(Outbound("m1", "accounts@abc-distributors.example.in", "Overdue invoices", "Body"))

    steps = [step for step, _ in RecordingSMTP.calls]
    assert steps == ["connect", "starttls", "login", "send"]
    sent = RecordingSMTP.calls[-1][1]
    assert isinstance(sent, EmailMessage)
    assert sent["To"] == "inbox@gmail.com" and sent["From"] == "me@gmail.com"
    assert sent["X-Original-To"] == "accounts@abc-distributors.example.in"
    assert sent["Subject"] == "[demo to accounts@abc-distributors.example.in] Overdue invoices"


# HACK-007: an address on EMAIL_ALLOW_REAL is mailed for real; every other customer still goes to the demo inbox.
@pytest.mark.parametrize(
    ("to", "expected"),
    [
        ("Riya@Gmail.com", "Riya@Gmail.com"),
        ("accounts@abc-distributors.example.in", "inbox@gmail.com"),
    ],
)
def test_only_allow_listed_addresses_get_real_mail(
    monkeypatch: pytest.MonkeyPatch, to: str, expected: str
) -> None:
    RecordingSMTP.calls = []
    monkeypatch.setattr(smtplib, "SMTP", RecordingSMTP)
    channel = EmailChannel(
        "smtp.gmail.com", 587, redirect_to="inbox@gmail.com", allow_real=" riya@gmail.com , me@gmail.com"
    )

    channel.send(Outbound("m1", to, "Overdue invoices", "Body"))

    sent = RecordingSMTP.calls[-1][1]
    assert isinstance(sent, EmailMessage)
    assert sent["To"] == expected


def test_a_real_smtp_account_without_a_demo_inbox_refuses_to_start() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://x:x@nowhere:1/x", smtp_user="me@gmail.com", email_redirect_to=""
    )

    with pytest.raises(RuntimeError, match="EMAIL_REDIRECT_TO"):
        create_app(settings)
