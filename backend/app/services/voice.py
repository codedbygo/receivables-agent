"""The AI voice collections call (HACK-003 F1).

    Collector clicks Call -> request(): flag, kill switch, consent, something to collect -> opening line
    each customer utterance -> turn(): intent() by rules (then the reply classifier), never by free model text
      -> a fixed action through the existing services (log_promise, log_dispute, a statement draft, escalate)
      -> the next AI line, rendered by code from the ledger and checked by verify() before it is spoken
    -> end(): status, outcome and a summary written by code; the timeline records the call.

What the customer says is untrusted, exactly like an email reply: it can choose an intent, never a tool, an
amount the ledger does not hold, or another customer's invoice. The AI line that fails verification is replaced by
a line with no figures. Nothing here marks anything paid; a "we paid" claim is checked against the ledger."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.classify import INVOICE, classify, dispute_category, dispute_reason, injection_suspected
from app.channels.voice import VoiceProvider
from app.core.clock import today
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr
from app.guardrails.verify import VerifyContext, verify
from app.llm.gateway import Gateway
from app.services import collections, disputes, drafting, ledger
from app.services.payments import verify_claim
from app.services.timeline import record

Kind = Literal[
    "promise",
    "dispute",
    "invoice_request",
    "payment_link",
    "payment_claim",
    "wrong_number",
    "unavailable",
    "balance_question",
    "yes",
    "no",
    "injection",
    "other",
]
RULES: tuple[tuple[Kind, re.Pattern[str]], ...] = (
    (
        "wrong_number",
        re.compile(
            r"\b(wrong number|no one by that name|not the right (person|number)|don'?t know (this|any))", re.I
        ),
    ),
    (
        "unavailable",
        re.compile(
            r"\b(not available|call (me )?(back )?later|in a meeting|busy right now|on leave)\b", re.I
        ),
    ),
    (
        "payment_link",
        re.compile(r"\b(payment link|pay(ing)? online|send (me |us )?(a |the )?link|upi link)\b", re.I),
    ),
    (
        "invoice_request",
        re.compile(
            r"\b(invoice (copy|copies|details)|send (me |us )?(the )?(invoices?|cop(y|ies)|details|statement)|"
            r"copies of)",
            re.I,
        ),
    ),
    (
        "balance_question",
        re.compile(
            r"\b(how much|what do (i|we) owe|which invoices|what is (the|my|our) (balance|outstanding))", re.I
        ),
    ),
)
YES = re.compile(r"^\s*(yes|yeah|yep|sure|ok(ay)?|please do|haan|ji)\b", re.I)
NO = re.compile(r"^\s*(no|nope|not now|no thanks)\b", re.I)
MAX_UNCLEAR = 2
MAX_SEQ = 38
SAFE_LINE = "A colleague will follow up with the exact details. Thank you for your time."
STATEMENT = (
    "Dear {name},\n\nAs discussed on our call, here are your open invoices:\n\n{{{{invoice_table}}}}\n\n"
    "Total outstanding: {{{{total}}}}\n\nPlease reply if anything does not match your books.\n\nRegards,\n"
    "Accounts team"
)


@dataclass(frozen=True)
class Intent:
    kind: Kind
    amount_paise: int | None = None
    on: date | None = None
    invoice: str | None = None
    category: str | None = None


def intent(
    said: str, d: date, open_invoices: list[str], gateway: Gateway | None, run_id: str | None = None
) -> Intent:
    """Fixed intents for a call: injection and call-only rules first, then the reply classifier (code parses
    amounts and dates from the customer's own words), then dispute categories."""
    if injection_suspected(said):
        return Intent("injection")
    for kind, rx in RULES:
        if rx.search(said):
            return Intent(kind)
    c = classify(said, d, open_invoices, gateway, run_id)
    refs = INVOICE.findall(said) or list(c.invoice_refs)
    if c.injection_suspected:
        return Intent("injection")
    if c.klass == "PROMISE":
        return Intent("promise", c.amount_paise, c.stated_date)
    if c.klass in ("PAYMENT_CONFIRMATION", "PART_PAYMENT"):
        return Intent("payment_claim", c.amount_paise, c.stated_date)
    if c.klass == "STATEMENT_REQUEST":
        return Intent("invoice_request")
    category = dispute_category(said)
    if c.klass == "DISPUTE" or (category != "other" and refs):
        return Intent("dispute", invoice=refs[0] if refs else None, category=category)
    if YES.match(said):
        return Intent("yes")
    if NO.match(said):
        return Intent("no")
    return Intent("other")


class Turn(BaseModel):
    seq: int
    speaker: Literal["ai", "customer"]
    text: str
    intent: str | None


class Call(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    provider: str
    simulated: bool
    status: str
    state: str
    outcome: str | None
    summary: str | None
    follow_up_on: date | None
    promise_id: str | None
    dispute_id: str | None
    started_at: datetime
    ended_at: datetime | None
    turns: list[Turn]


def get_call(session: Session, call_id: str) -> Call:
    r = (
        session.execute(
            text("""SELECT k.id::text, k.customer_id::text, c.name AS customer_name, k.provider, k.simulated,
        k.status, k.state, k.outcome, k.summary, k.follow_up_on, k.promise_id::text, k.dispute_id::text,
        k.started_at, k.ended_at FROM calls k JOIN customers c ON c.id = k.customer_id WHERE k.id = CAST(:k AS uuid)"""),
            {"k": call_id},
        )
        .mappings()
        .first()
    )
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Call not found.")
    turns = [
        Turn(**t)
        for t in session.execute(
            text(
                "SELECT seq, speaker, text, intent FROM call_turns WHERE call_id = CAST(:k AS uuid) ORDER BY seq"
            ),
            {"k": call_id},
        ).mappings()
    ]
    return Call(**r, turns=turns)


def list_calls(session: Session, customer_id: str | None, limit: int = 20) -> list[Call]:
    ids: list[str] = list(
        session.execute(
            text("""SELECT id::text FROM calls WHERE (CAST(:c AS uuid) IS NULL OR customer_id = CAST(:c AS uuid))
        ORDER BY started_at DESC LIMIT :l"""),
            {"c": customer_id, "l": limit},
        ).scalars()
    )
    return [get_call(session, str(i)) for i in ids]


def _chase(session: Session, customer_id: str) -> list[ledger.Invoice]:
    d = today(session)
    return [
        i
        for i in ledger.customer_invoices(session, d, customer_id)
        if i.remaining_paise > 0 and i.status != "disputed"
    ]


def _say(session: Session, call_id: str, customer_id: str, line: str) -> str:
    """Store and return the AI line, or SAFE_LINE when the verifier does not pass every figure in it."""
    facts, names = drafting._facts(session)
    disputed, promises = drafting.customer_state(session, customer_id)
    name = session.execute(
        text("SELECT name FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id}
    ).scalar()
    report = verify(
        line,
        VerifyContext(
            customer=str(name),
            cited=tuple(i.number for i in _chase(session, customer_id)),
            invoices=facts,
            customer_names=names,
            today=today(session),
            kind="reminder",
            promise_amounts=tuple(p.amount_paise for p in promises),
            promise_dates=tuple(p.promised_date for p in promises),
            disputed=disputed,
        ),
    )
    if not report.ok:
        for c in report.checks:
            if not c.ok:
                session.execute(
                    text("""INSERT INTO guardrail_events (check_name, code, customer_id, detail)
                    VALUES (:n, :code, CAST(:c AS uuid), CAST(:d AS jsonb))"""),
                    {"n": c.check, "code": c.code, "c": customer_id, "d": '{"source": "voice_call"}'},
                )
        line = SAFE_LINE
    _turn(session, call_id, "ai", line, None)
    return line


def _turn(session: Session, call_id: str, speaker: str, said: str, kind: str | None) -> None:
    session.execute(
        text("""INSERT INTO call_turns (call_id, seq, speaker, text, intent) VALUES (CAST(:k AS uuid),
        (SELECT COALESCE(MAX(seq), 0) + 1 FROM call_turns WHERE call_id = CAST(:k AS uuid)), :s, :t, :i)"""),
        {"k": call_id, "s": speaker, "t": said[:2000], "i": kind},
    )


def opening_line(chase: list[tuple[str, int, date]]) -> str:
    """The first line of every call, from (number, remaining, due) of the invoices being chased."""
    total = sum(r for _, r, _ in chase)
    oldest = min((d for _, _, d in chase), default=None)
    n = len(chase)
    return (
        "Hello, this is the automated collections assistant calling from the accounts team. This call is not "
        f"recorded. I am calling about your outstanding balance of {format_inr(total)} across {n} invoice"
        f"{'s' if n != 1 else ''}"
        + (f"; the oldest was due on {oldest:%d %b %Y}" if oldest else "")
        + ". Could you let us know when we can expect payment?"
    )


def balance_line(chase: list[tuple[str, int, date]]) -> str:
    lines = "; ".join(f"{n} for {format_inr(r)}" for n, r, _ in chase)
    return f"Your open invoices are {lines}. Together that is {format_inr(sum(r for _, r, _ in chase))}. When can you pay?"


def promise_line(amount_paise: int, on: date) -> str:
    return (
        f"Thank you. I have recorded a payment promise of {format_inr(amount_paise)} for {on:%d %b %Y}. "
        "Would you like us to send you the invoice details?"
    )


def _rows(chase: list[ledger.Invoice]) -> list[tuple[str, int, date]]:
    return [(i.number, i.remaining_paise, i.due_date) for i in chase]


def opening(session: Session, customer_id: str) -> str:
    return opening_line(_rows(_chase(session, customer_id)))


def request(session: Session, customer_id: str, user_id: str, provider: VoiceProvider) -> Call:
    """Start a call. Every gate a message has applies: the voice flag, the kill switch, the customer's consent,
    and something to collect that is not under dispute."""
    s = session.execute(text("SELECT feature_voice, sending_enabled FROM settings WHERE id = 1")).one()
    if not s.feature_voice:
        raise AppError(ErrorCode.FEATURE_DISABLED, "Voice calls are switched off.")
    if not s.sending_enabled:
        raise AppError(ErrorCode.SENDING_DISABLED, "The kill switch is on: no calls and no messages.")
    c = session.execute(
        text("""SELECT phone, COALESCE((contact_consent ->> 'voice')::boolean, false) AS ok FROM customers
        WHERE id = CAST(:c AS uuid)"""),
        {"c": customer_id},
    ).first()
    if c is None:
        raise AppError(ErrorCode.NOT_FOUND, "Customer not found.")
    if not c.ok:
        raise AppError(ErrorCode.FEATURE_DISABLED, "The customer has not agreed to voice calls.")
    if not _chase(session, customer_id):
        raise AppError(ErrorCode.VALIDATION_ERROR, "Nothing to collect outside disputed invoices.")
    try:
        with session.begin_nested():
            call_id = str(
                session.execute(
                    text("""INSERT INTO calls (customer_id, requested_by, provider, simulated, status, state)
                    VALUES (CAST(:c AS uuid), CAST(:u AS uuid), :p, :sim, 'in_progress', 'listening') RETURNING id::text"""),
                    {"c": customer_id, "u": user_id, "p": provider.name, "sim": provider.simulated},
                ).scalar_one()
            )
    except IntegrityError:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "A call with this customer is already in progress."
        ) from None
    record(
        session,
        customer_id,
        "call_requested",
        "human",
        "Call requested" + (" (SIMULATED provider: no phone rings)" if provider.simulated else ""),
        ref_type="call",
        ref_id=call_id,
        actor_user_id=user_id,
    )
    _say(session, call_id, customer_id, opening(session, customer_id))
    # ponytail: the provider call happens inside this transaction (10 s timeout); a queue if calls get slow
    pid = provider.place(call_id, c.phone)
    session.execute(
        text("UPDATE calls SET provider_call_id = :p WHERE id = CAST(:k AS uuid)"), {"p": pid, "k": call_id}
    )
    return get_call(session, call_id)


def _lock(session: Session, call_id: str) -> tuple[str, str, int, str | None]:
    r = session.execute(
        text("""SELECT customer_id::text, status, state, unclear_turns, promise_id::text,
        (SELECT COALESCE(MAX(seq), 0) FROM call_turns WHERE call_id = k.id) AS seq
        FROM calls k WHERE id = CAST(:k AS uuid) FOR UPDATE"""),
        {"k": call_id},
    ).first()
    if r is None:
        raise AppError(ErrorCode.NOT_FOUND, "Call not found.")
    if r.status != "in_progress":
        raise AppError(ErrorCode.VALIDATION_ERROR, f"This call is {r.status.replace('_', ' ')}.")
    return str(r.customer_id), str(r.state), int(r.seq), r.promise_id


def turn(session: Session, call_id: str, said: str, gateway: Gateway | None) -> Call:
    """One customer utterance (speech to text from the provider, or typed by a collector on a simulated call)."""
    said = said.strip()
    if not said or len(said) > 2000:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Say something under 2,000 characters.")
    cid, state, seq, promise_id = _lock(session, call_id)
    if not session.execute(text("SELECT sending_enabled FROM settings WHERE id = 1")).scalar():
        # The kill switch stops live calls too: one polite line, no action on what was said, then hang up.
        _turn(session, call_id, "customer", said, None)
        _say(session, call_id, cid, "I am sorry, I have to end this call now. A colleague will contact you.")
        return end(session, call_id, "completed", "promise" if promise_id else "no_commitment")
    chase = _chase(session, cid)
    it = intent(said, today(session), [i.number for i in chase], gateway)
    _turn(session, call_id, "customer", said, it.kind)
    end_with: tuple[str, str] | None = None  # (status, outcome)
    k = it.kind

    if k == "injection":
        _say(session, call_id, cid, "Thank you. A member of our team will call you back.")
        collections.escalate(session, cid, "injection_suspected", "Instruction-like speech on a call")
        session.execute(
            text("""INSERT INTO guardrail_events (check_name, code, customer_id, detail)
            VALUES ('injection', 'PROMPT_INJECTION_SUSPECTED', CAST(:c AS uuid), '{"source": "voice_call"}'::jsonb)"""),
            {"c": cid},
        )
        end_with = ("completed", "escalated")
    elif k == "wrong_number":
        _say(session, call_id, cid, "Sorry for the trouble. We will update our records. Goodbye.")
        collections.escalate(
            session, cid, "low_confidence", "Wrong number on a call: check the contact details"
        )
        end_with = ("wrong_number", "wrong_number")
    elif k == "unavailable":
        _say(session, call_id, cid, "No problem. We will call back another time. Goodbye.")
        _follow_up(session, call_id, today(session) + timedelta(days=1))
        end_with = ("completed", "unavailable")
    elif k == "balance_question":
        _say(session, call_id, cid, balance_line(_rows(chase)))
    elif k == "promise" and it.amount_paise and it.on:
        if it.amount_paise > sum(i.remaining_paise for i in chase):
            _say(session, call_id, cid, "That is more than the open balance. Could you confirm the amount?")
        else:
            p = collections.log_promise(session, cid, it.amount_paise, it.on, actor="customer")
            session.execute(
                text("""UPDATE calls SET promise_id = CAST(:p AS uuid), follow_up_on = :d, state = 'offered_details'
                WHERE id = CAST(:k AS uuid)"""),
                {"p": p.id, "d": it.on, "k": call_id},
            )
            _say(session, call_id, cid, promise_line(it.amount_paise, it.on))
    elif k == "promise":
        _unclear(session, call_id, cid, "Could you tell me the amount and the date you plan to pay?")
    elif k == "dispute":
        end_with = _dispute(session, call_id, cid, it, said, [i.number for i in chase])
    elif k == "invoice_request" or (k == "yes" and state == "offered_details"):
        _statement(session, call_id, cid)
        _say(
            session,
            call_id,
            cid,
            "I will arrange for the invoice details to be sent to you. Thank you, goodbye.",
        )
        end_with = ("completed", "promise" if promise_id else "invoice_request")
    elif k == "no" and state == "offered_details":
        _say(session, call_id, cid, "Thank you for your time. Goodbye.")
        end_with = ("completed", "promise")
    elif k == "payment_link":
        _say(
            session,
            call_id,
            cid,
            "I will ask a colleague to send you a secure payment link. Thank you, goodbye.",
        )
        end_with = ("completed", "promise" if promise_id else "payment_link_request")
    elif k == "payment_claim":
        if verify_claim(session, cid, it.amount_paise, it.on) is None:  # never marks anything paid (REQ-078)
            collections.escalate(
                session, cid, "claim_not_found", "Payment claimed on a call; not in the ledger"
            )
        _say(
            session, call_id, cid, "Thank you. We will check our bank records and confirm by email. Goodbye."
        )
        end_with = ("completed", "payment_claim")
    elif state == "offered_details":
        _say(session, call_id, cid, "Thank you for your time. Goodbye.")
        end_with = ("completed", "promise")
    elif not _unclear(session, call_id, cid, "Sorry, could you tell me when you can make the payment?"):
        end_with = ("completed", "promise" if promise_id else "no_commitment")
    if end_with is None and seq + 2 >= MAX_SEQ:
        _say(session, call_id, cid, SAFE_LINE)
        end_with = ("completed", "promise" if promise_id else "no_commitment")
    if end_with:
        end(session, call_id, *end_with)
    return get_call(session, call_id)


def _unclear(session: Session, call_id: str, cid: str, ask: str) -> bool:
    """Ask again, up to MAX_UNCLEAR times. Returns False when the call should end instead."""
    n: int = session.execute(
        text(
            "UPDATE calls SET unclear_turns = unclear_turns + 1 WHERE id = CAST(:k AS uuid) RETURNING unclear_turns"
        ),
        {"k": call_id},
    ).scalar_one()
    if n > MAX_UNCLEAR:
        _say(session, call_id, cid, SAFE_LINE)
        return False
    _say(session, call_id, cid, ask)
    return True


def _follow_up(session: Session, call_id: str, on: date) -> None:
    session.execute(
        text("UPDATE calls SET follow_up_on = :d WHERE id = CAST(:k AS uuid)"), {"d": on, "k": call_id}
    )


def _dispute(
    session: Session, call_id: str, cid: str, it: Intent, said: str, open_numbers: list[str]
) -> tuple[str, str] | None:
    if it.invoice is None or it.invoice not in open_numbers:  # another customer's or an unknown invoice: ask
        _unclear(session, call_id, cid, "Which of your invoice numbers is this about?")
        return None
    try:
        d = collections.log_dispute(session, cid, it.invoice, dispute_reason(said), actor="customer")
    except AppError:  # already disputed
        _say(session, call_id, cid, f"{it.invoice} is already with our team. They will contact you. Goodbye.")
        return ("completed", "dispute")
    session.execute(
        text("UPDATE calls SET dispute_id = CAST(:d AS uuid) WHERE id = CAST(:k AS uuid)"),
        {"d": d.id, "k": call_id},
    )
    team = disputes.TEAM_LABEL.get(d.assigned_team or "collections", "Collections")
    _say(
        session,
        call_id,
        cid,
        f"Thank you, I have noted your concern about {it.invoice}. Our {team} team will contact you, and we will "
        "not chase that invoice in the meantime. Goodbye.",
    )
    return ("completed", "dispute")


def _statement(session: Session, call_id: str, cid: str) -> None:
    """The invoice details as a statement draft: it waits for approval like every message."""
    name = session.execute(
        text("SELECT name FROM customers WHERE id = CAST(:c AS uuid)"), {"c": cid}
    ).scalar()
    try:
        drafting.draft_message(
            session, cid, "statement", STATEMENT.format(name=name), "gentle", "email", actor="ai"
        )
    except AppError:
        return  # nothing open to list: the summary still says what was asked


def end(session: Session, call_id: str, status: str, outcome: str) -> Call:
    """Close the call with a summary written by code from the call row and the ledger."""
    r = session.execute(
        text("""SELECT k.customer_id::text, k.simulated, k.follow_up_on, p.amount_paise, p.promised_date,
        (SELECT i.number FROM disputes d JOIN invoices i ON i.id = d.invoice_id WHERE d.id = k.dispute_id) AS inv
        FROM calls k LEFT JOIN promises p ON p.id = k.promise_id WHERE k.id = CAST(:k AS uuid)"""),
        {"k": call_id},
    ).one()
    parts = [
        f"Call {status.replace('_', ' ')}" + (" (SIMULATED)" if r.simulated else ""),
        f"Outcome: {outcome.replace('_', ' ')}",
    ]
    if r.amount_paise:
        parts += [
            f"Promise amount: {format_inr(r.amount_paise)}",
            f"Promise date: {r.promised_date:%d %b %Y}",
        ]
    if r.inv:
        parts.append(f"Dispute on {r.inv}, routed to a team")
    nxt = {
        "promise": f"Follow up on {r.follow_up_on:%d %b %Y}" if r.follow_up_on else "Watch for the payment",
        "dispute": "The assigned team contacts the customer",
        "invoice_request": "Approve the statement draft",
        "payment_link_request": "Send a payment link",
        "payment_claim": "Check the bank feed for the claimed payment",
        "wrong_number": "Correct the phone number",
        "unavailable": f"Call again on {r.follow_up_on:%d %b %Y}" if r.follow_up_on else "Call again",
        "escalated": "A collector reviews the call",
    }.get(outcome, "A collector decides the next step")
    parts.append(f"Next action: {nxt}")
    summary = ". ".join(parts) + "."
    session.execute(
        text("""UPDATE calls SET status = :s, outcome = :o, state = 'ended', summary = :sum, ended_at = now()
        WHERE id = CAST(:k AS uuid)"""),
        {"s": status, "o": outcome, "sum": summary, "k": call_id},
    )
    record(
        session,
        r.customer_id,
        "call_completed" if status == "completed" else "call_failed",
        "ai",
        summary[:300],
        amount_paise=r.amount_paise,
        ref_type="call",
        ref_id=call_id,
    )
    return get_call(session, call_id)


def hang_up(session: Session, call_id: str) -> Call:
    """A collector ends a call (or the provider reports it ended) before an outcome was reached."""
    _, _, _, promise_id = _lock(session, call_id)
    return end(session, call_id, "completed", "promise" if promise_id else "no_commitment")


def provider_status(session: Session, call_id: str, provider_status_: str) -> None:
    """Twilio's status callback: a call that never connected is failed or unanswered."""
    status = {"no-answer": "no_answer", "busy": "no_answer", "failed": "failed", "canceled": "failed"}.get(
        provider_status_
    )
    active = session.execute(
        text("SELECT status = 'in_progress' FROM calls WHERE id = CAST(:k AS uuid) FOR UPDATE"),
        {"k": call_id},
    ).scalar()
    if not active:
        return
    if status:
        end(session, call_id, status, "failed")
    elif provider_status_ == "completed":
        hang_up(session, call_id)
