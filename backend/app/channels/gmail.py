"""Email through the connected company Google account (HACK-009, ADR-0018): the same message the SMTP channel
builds, sent with the Gmail API so it sits in the account's Sent folder and its thread can be read for replies."""

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.channels.email import ChannelError, Outbound, compose
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services import google

SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailChannel:
    name = "email"
    simulated = False

    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings
        self.allow_real = {a.strip().lower() for a in settings.email_allow_real.split(",") if a.strip()}

    def send(self, message: Outbound) -> str:
        """Returns the Gmail thread id, stored on the message so a reply in that thread finds its customer."""
        try:
            with Session(self.engine) as s:
                g = google.client(s, self.settings)
            m = compose(message, g.email, self.settings.email_redirect_to, self.allow_real)
            sent = g.call("POST", SEND, json={"raw": google.b64url(m.as_bytes())})
        except AppError as e:
            # Not connected is a setup problem a retry cannot fix; Google being down is worth retrying.
            raise ChannelError(str(e.code), retryable=e.code == ErrorCode.GOOGLE_UPSTREAM) from e
        return str(sent["threadId"])
