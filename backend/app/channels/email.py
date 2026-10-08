"""Channels (REQ-059 to REQ-061, LLD 7.2). Email is real SMTP (Mailpit in the demo)."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


@dataclass(frozen=True)
class Outbound:
    message_id: str
    to: str
    subject: str
    body: str


class ChannelError(Exception):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code, self.retryable = code, retryable


class MessageChannel(Protocol):
    name: str
    simulated: bool  # HACK-003: stored on the message and shown; a simulator never passes for a real provider

    def send(self, message: Outbound) -> str: ...


def compose(message: Outbound, from_addr: str, redirect_to: str, allow_real: set[str]) -> EmailMessage:
    """The email as sent, shared by SMTP and Gmail (HACK-009) so both follow the same redirect rule."""
    m = EmailMessage()
    m["From"] = from_addr
    if redirect_to and message.to.strip().lower() not in allow_real:
        # optional (ADR-0017): with a redirect inbox set, every mail goes there except the allow-listed
        # addresses; with none set, every customer is mailed at their own address
        m["To"] = redirect_to
        m["X-Original-To"] = message.to
        m["Subject"] = f"[demo to {message.to}] {message.subject}"
    else:
        m["To"] = message.to
        m["Subject"] = message.subject
    m["Message-ID"] = f"<{message.message_id}@collections.local>"
    m.set_content(message.body)
    return m


class EmailChannel:
    name = "email"
    simulated = False  # real SMTP (Mailpit, a test inbox, in the local demo)

    def __init__(
        self,
        host: str,
        port: int,
        *,
        username: str = "",
        password: str = "",
        starttls: bool = False,
        from_addr: str = "",
        redirect_to: str = "",
        allow_real: str = "",
    ) -> None:
        self.host, self.port = host, port
        self.username, self.password, self.starttls = username, password, starttls
        self.from_addr = from_addr or "Accounts team <collections@demo-business.example.in>"
        self.redirect_to = redirect_to
        self.allow_real = {a.strip().lower() for a in allow_real.split(",") if a.strip()}

    def send(self, message: Outbound) -> str:
        m = compose(message, self.from_addr, self.redirect_to, self.allow_real)
        accepted = False
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                if self.starttls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(m)
                accepted = True
        except (OSError, smtplib.SMTPException) as e:
            if (
                not accepted
            ):  # an error in QUIT after the server accepted the mail must not cause a second send
                raise ChannelError("SMTP_UNAVAILABLE", retryable=True) from e
        return str(m["Message-ID"])


class WhatsAppChannel:
    """Simulated and provider-pluggable (REQ-060): records the send and returns a provider id."""

    name = "whatsapp"
    simulated = True

    def send(self, message: Outbound) -> str:
        return f"sim-wa-{message.message_id}"
