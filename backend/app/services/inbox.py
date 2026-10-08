"""Customer replies read from Gmail (HACK-009, closes D-001): only threads the app started are read, and each new
customer email waits in a review queue until a collector accepts it (then it is classified like a pasted reply)
or dismisses it (an out-of-office, a thank-you)."""

import base64
import re
from datetime import UTC, datetime
from email.utils import parseaddr
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.agent import replies
from app.agent.orchestrator import Orchestrator
from app.core.config import Settings
from app.core.db import transaction
from app.core.errors import AppError, ErrorCode
from app.services import google, overview

THREADS = "https://gmail.googleapis.com/gmail/v1/users/me/threads"
MAX_THREADS = (
    200  # ponytail: one GET per thread with a sent reminder in 60 days; Gmail history or push if it grows
)
# Where the quoted history starts: "On <date>, <name> wrote:" (may wrap), Outlook's divider, or quoted lines.
QUOTED = re.compile(r"^(On .{0,300}?wrote:|-{2,} ?Original Message ?-{2,}|>)", re.M | re.S)


class Inbound(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    message_id: str
    message_subject: str
    from_address: str
    subject: str
    body: str
    received_at: datetime
    status: str


def _text(part: dict[str, Any]) -> str:
    """The first text/plain body anywhere in a Gmail payload."""
    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
        data = part["body"]["data"]
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    for child in part.get("parts", []):
        if found := _text(child):
            return found
    return ""


def new_text(body: str) -> str:
    """The reply without the quoted reminder underneath it."""
    m = QUOTED.search(body)
    return (body[: m.start()] if m else body).strip()


def poll(engine: Engine, settings: Settings) -> int:
    """Queue every customer email not seen before in the threads of sent reminders. Returns how many."""
    with Session(engine) as s:
        g = google.client(s, settings)
        threads = s.execute(
            text("""SELECT DISTINCT ON (provider_ref) provider_ref, id::text AS message_id, customer_id::text AS customer_id
            FROM messages WHERE channel = 'email' AND status = 'sent' AND provider_ref IS NOT NULL
              AND sent_at > now() - interval '60 days'
            ORDER BY provider_ref, sent_at DESC LIMIT :n"""),
            {"n": MAX_THREADS},
        ).all()
        seen = set(s.execute(text("SELECT gmail_message_id FROM inbound_emails")).scalars())
    found = 0
    for t in threads:
        for msg in g.call("GET", f"{THREADS}/{t.provider_ref}", params={"format": "full"}).get(
            "messages", []
        ):
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            sender = parseaddr(headers.get("from", ""))[1].lower()
            if msg["id"] in seen or "SENT" in msg.get("labelIds", []) or sender == g.email.lower():
                continue  # already queued, or one of ours
            body = new_text(_text(msg.get("payload", {})) or str(msg.get("snippet", "")))[
                : replies.MAX_REPLY_CHARS
            ]
            with engine.begin() as c:
                c.execute(
                    text("""INSERT INTO inbound_emails (gmail_message_id, message_id, customer_id, from_address,
                    subject, body, received_at) VALUES (:g, CAST(:m AS uuid), CAST(:c AS uuid), :f, :s, :b, :r)
                    ON CONFLICT (gmail_message_id) DO NOTHING"""),
                    {
                        "g": msg["id"],
                        "m": t.message_id,
                        "c": t.customer_id,
                        "f": sender or headers.get("from", "unknown"),
                        "s": headers.get("subject", "")[:500],
                        "b": body or "(no text)",
                        "r": datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000, UTC),
                    },
                )
            seen.add(msg["id"])
            found += 1
    return found


_LIST = """SELECT i.id::text AS id, i.customer_id::text AS customer_id, c.name AS customer_name,
  i.message_id::text AS message_id, m.subject AS message_subject, i.from_address, i.subject, i.body,
  i.received_at, i.status
FROM inbound_emails i JOIN customers c ON c.id = i.customer_id JOIN messages m ON m.id = i.message_id"""


def pending(session: Session, limit: int = 100) -> list[Inbound]:
    rows = session.execute(
        text(_LIST + " WHERE i.status = 'pending' ORDER BY i.received_at LIMIT :n"), {"n": limit}
    ).mappings()
    return [Inbound(**r) for r in rows]


def _claim(session: Session, inbound_id: str) -> Any:
    row = session.execute(
        text(
            "SELECT message_id::text AS message_id, body, status FROM inbound_emails WHERE id = CAST(:i AS uuid) FOR UPDATE"
        ),
        {"i": inbound_id},
    ).first()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Incoming reply not found.")
    if row.status != "pending":
        raise AppError(ErrorCode.STALE_DRAFT, f"This reply was already {row.status}.")
    return row


def accept(orch: Orchestrator, inbound_id: str, user_id: str) -> overview.ReplyRow:
    """The collector confirms it is a real reply: stored and classified exactly like a pasted one."""
    with transaction(orch.sessions) as s:
        row = _claim(s, inbound_id)
        rid, _customer = replies.ingest(s, row.message_id, row.body)
        s.execute(
            text("""UPDATE inbound_emails SET status = 'accepted', reply_id = CAST(:r AS uuid),
            reviewed_by = CAST(:u AS uuid), reviewed_at = now() WHERE id = CAST(:i AS uuid)"""),
            {"r": rid, "u": user_id, "i": inbound_id},
        )
    replies.understand(orch, rid)
    with orch.sessions() as s:
        return overview.get_reply(s, rid)


def dismiss(session: Session, inbound_id: str, user_id: str) -> Inbound:
    _claim(session, inbound_id)
    session.execute(
        text("""UPDATE inbound_emails SET status = 'dismissed', reviewed_by = CAST(:u AS uuid), reviewed_at = now()
        WHERE id = CAST(:i AS uuid)"""),
        {"u": user_id, "i": inbound_id},
    )
    row = session.execute(text(_LIST + " WHERE i.id = CAST(:i AS uuid)"), {"i": inbound_id}).mappings().one()
    return Inbound(**row)
