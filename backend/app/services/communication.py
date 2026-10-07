"""The collection communication service (HACK-003 F2): which channel to use next, and why.

The cadence (policy cadence: day 1 email, day 3 WhatsApp, day 7 voice, day 10 a person) gives the step; the
customer's preference, the feature flags and the customer's consent can change it. This service only decides:
drafts still wait for approval and every send still goes through approval.send_gate."""

import json
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.guardrails.verify import policy
from app.services.timeline import record

Channel = Literal["email", "whatsapp", "sms", "voice", "human"]
MESSAGING = ("email", "whatsapp", "sms")
LABEL = {"email": "Email", "whatsapp": "WhatsApp", "sms": "SMS", "voice": "a voice call", "human": "a person"}
CYCLE_DAYS = 45  # contacts older than this start a new cycle


class ChannelPlan(BaseModel):
    preferred_channel: str | None
    last_channel: str | None
    last_contact_on: date | None
    response_status: Literal["never contacted", "no response", "replied"]
    cadence_day: int
    recommended_channel: str
    draft_channel: Literal["email", "whatsapp", "sms"]
    next_step_channel: str | None
    next_step_on: date | None
    factors: list[str]
    consent: dict[str, bool]  # what the customer agreed to beyond email (always on), for the preferences form


def choose(
    *,
    first_contact: date | None,
    today: date,
    preferred: str | None,
    enabled: dict[str, bool],
    consent: dict[str, bool],
    replied: bool,
    last_channel: str | None,
    last_contact_on: date | None = None,
) -> ChannelPlan:
    """Pure: the cadence step for today, then preference, flags and consent, each stated as a factor."""
    cadence = policy().cadence
    day = 1 if first_contact is None else (today - first_contact).days + 1
    step = max((c for c in cadence if c[0] <= day), default=cadence[0])
    channel = step[1]
    factors = [f"Day {day} of the cadence: {LABEL[channel]} (policy cadence)"]

    def usable(ch: str) -> str | None:
        """Why a channel cannot be used now, or None."""
        if ch in ("email", "human"):
            return None
        if not enabled.get(ch, False):
            return f"{LABEL[ch]} is switched off"
        if not consent.get(ch, False):
            return f"the customer has not agreed to {LABEL[ch]}"
        return None

    if replied:
        channel = last_channel if last_channel in MESSAGING else "email"
        factors.append(f"The customer replied: answer on {LABEL[channel]}")
    elif (
        channel in MESSAGING and preferred in MESSAGING and preferred != channel and usable(preferred) is None
    ):
        channel = preferred
        factors.append(f"The customer prefers {LABEL[preferred]}")
    if (why := usable(channel)) is not None:
        factors.append(f"{why[0].upper()}{why[1:]}: email instead")
        channel = "email"
    later = [c for c in cadence if c[0] > day]
    nxt = later[0] if later and first_contact is not None else None
    return ChannelPlan(
        preferred_channel=preferred,
        last_channel=last_channel,
        last_contact_on=last_contact_on,
        response_status="never contacted"  # no send in any cycle, not only since the last payment (HACK-004)
        if first_contact is None and last_contact_on is None
        else "replied"
        if replied
        else "no response",
        cadence_day=day,
        recommended_channel=channel,
        draft_channel=channel if channel in MESSAGING else "email",
        next_step_channel=nxt[1] if nxt else None,
        next_step_on=first_contact + timedelta(days=nxt[0] - 1) if nxt and first_contact else None,
        factors=factors,
        consent={ch: consent.get(ch, False) for ch in ("whatsapp", "sms", "voice")},
    )


def plan(session: Session, customer_id: str, today: date) -> ChannelPlan:
    """The inputs to choose() from the database: sends (timeline business dates), replies, the last payment."""
    r = session.execute(
        text("""WITH sends AS (
          SELECT t.business_date, m.channel, m.sent_at FROM timeline_events t
          JOIN messages m ON m.id = t.ref_id WHERE t.customer_id = CAST(:c AS uuid) AND t.kind = 'sent'),
        paid AS (SELECT max(received_on) AS on_ FROM payments WHERE customer_id = CAST(:c AS uuid)
          AND match_status = 'matched')
        SELECT c.preferred_channel, c.contact_consent,
          (SELECT min(business_date) FROM sends WHERE business_date > COALESCE((SELECT on_ FROM paid), 'epoch')
             AND business_date > CAST(:d AS date) - :cycle) AS first_contact,
          (SELECT channel FROM sends ORDER BY sent_at DESC LIMIT 1) AS last_channel,
          (SELECT business_date FROM sends ORDER BY sent_at DESC LIMIT 1) AS last_on,
          EXISTS (SELECT 1 FROM replies rp WHERE rp.customer_id = c.id
            AND rp.received_at > COALESCE((SELECT max(sent_at) FROM sends), 'epoch')) AND EXISTS (SELECT 1 FROM sends)
            AS replied,
          s.feature_whatsapp, s.feature_sms, s.feature_voice
        FROM customers c, settings s WHERE c.id = CAST(:c AS uuid) AND s.id = 1"""),
        {"c": customer_id, "d": today, "cycle": CYCLE_DAYS},
    ).first()
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    return choose(
        first_contact=r.first_contact,
        today=today,
        preferred=r.preferred_channel,
        enabled={"whatsapp": r.feature_whatsapp, "sms": r.feature_sms, "voice": r.feature_voice},
        consent={str(k): bool(v) for k, v in (r.contact_consent or {}).items()},
        replied=bool(r.replied),
        last_channel=r.last_channel,
        last_contact_on=r.last_on,
    )


def set_preferences(
    session: Session, customer_id: str, preferred: str | None, consent: dict[str, bool], user_id: str
) -> None:
    """A collector records the customer's preferred channel and what they agreed to (HACK-003 F2)."""

    if preferred is not None and preferred not in ("email", "whatsapp", "sms", "voice"):
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Unknown channel {preferred}.")
    if preferred is not None and preferred != "email" and not consent.get(preferred, False):
        raise AppError(ErrorCode.VALIDATION_ERROR, "A preferred channel needs the customer's consent first.")
    done = session.execute(
        text("""UPDATE customers SET preferred_channel = :p, contact_consent = CAST(:c AS jsonb)
        WHERE id = CAST(:id AS uuid) RETURNING id"""),
        {"p": preferred, "c": json.dumps({"email": True, **consent}), "id": customer_id},
    ).scalar()
    if done is None:
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    agreed = ", ".join(LABEL[k] for k, v in consent.items() if v and k in LABEL) or "email only"
    record(
        session,
        customer_id,
        "contact_preferences_changed",
        "human",
        f"Contact preferences: prefers {LABEL.get(preferred or 'email', 'Email')}; agreed to {agreed}",
        actor_user_id=user_id,
    )
