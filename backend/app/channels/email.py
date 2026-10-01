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

    def send(self, message: Outbound) -> str: ...


class EmailChannel:
    name = "email"

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port

    def send(self, message: Outbound) -> str:
        m = EmailMessage()
        m["From"] = "Accounts team <collections@demo-business.example.in>"
        m["To"] = message.to
        m["Subject"] = message.subject
        m["Message-ID"] = f"<{message.message_id}@collections.local>"
        m.set_content(message.body)
        accepted = False
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
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

    def send(self, message: Outbound) -> str:
        return f"sim-wa-{message.message_id}"
