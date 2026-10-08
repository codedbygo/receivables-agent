"""Google Calendar kept in step with the ledger (HACK-009): one all-day event per open promise and per open
follow-up task, removed once the promise is settled or the task closed. The ledger stays the source; the calendar
only mirrors it, so a sync can always be run again."""

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.money import format_inr
from app.services import google

EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

_WANTED = text("""
SELECT 'promise' AS ref_type, p.id::text AS ref_id, p.customer_id::text AS customer_id, c.name,
  p.promised_date AS day, p.amount_paise AS amount, NULL AS action
FROM promises p JOIN customers c ON c.id = p.customer_id WHERE p.status = 'pending'
UNION ALL
SELECT 'follow_up', f.id::text, f.customer_id::text, c.name, f.due_on, NULL, f.recommended_action
FROM follow_up_tasks f JOIN customers c ON c.id = f.customer_id WHERE f.status = 'open'
""")


class CalendarSync(BaseModel):
    created: int
    removed: int


def _event(r: Any, settings: Settings) -> dict[str, Any]:
    parts = urlsplit(settings.google_redirect_uri)
    link = f"{parts.scheme}://{parts.netloc}/#/customers/{r['customer_id']}"
    day: date = r["day"]
    if r["ref_type"] == "promise":
        summary = f"{r['name']} promised {format_inr(r['amount'])}"
        detail = "Promise to pay is due today. The app marks it fulfilled or missed from the bank feed."
    else:
        summary = f"Follow up: {r['name']}"
        detail = str(r["action"])
    return {
        "summary": summary,
        "description": f"{detail}\n\nCustomer: {link}",
        "start": {"date": day.isoformat()},
        "end": {"date": (day + timedelta(days=1)).isoformat()},
    }


def sync(engine: Engine, settings: Settings) -> CalendarSync:
    """Create the missing events and remove the stale ones. Each event is recorded in its own transaction right
    after Google accepts it, so a failure part-way never leaves an event the database does not know about."""
    with Session(engine) as s:
        g = google.client(s, settings)
        wanted = {(r["ref_type"], r["ref_id"]): r for r in s.execute(_WANTED).mappings().all()}
        have = {
            (r.ref_type, r.ref_id): r.google_event_id
            for r in s.execute(
                text("SELECT ref_type, ref_id::text AS ref_id, google_event_id FROM calendar_events")
            )
        }
    created = removed = 0
    for key, r in wanted.items():
        if key in have:
            continue
        event = g.call("POST", EVENTS, json=_event(r, settings))
        with engine.begin() as c:
            c.execute(
                text("""INSERT INTO calendar_events (ref_type, ref_id, customer_id, google_event_id)
                VALUES (:t, CAST(:r AS uuid), CAST(:c AS uuid), :e) ON CONFLICT DO NOTHING"""),
                {"t": key[0], "r": key[1], "c": r["customer_id"], "e": event["id"]},
            )
        created += 1
    for key, event_id in have.items():
        if key in wanted:
            continue
        g.call("DELETE", f"{EVENTS}/{event_id}")
        with engine.begin() as c:
            c.execute(
                text("DELETE FROM calendar_events WHERE ref_type = :t AND ref_id = CAST(:r AS uuid)"),
                {"t": key[0], "r": key[1]},
            )
        removed += 1
    return CalendarSync(created=created, removed=removed)
