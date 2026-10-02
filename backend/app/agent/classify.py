"""Reply classification (REQ-064 to REQ-068). The model labels the reply and copies spans; code parses
and validates every value. With no model available, deterministic rules classify instead."""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast

from app.core.clock import DateInvalidError, resolve_date
from app.core.money import parse_amounts
from app.guardrails.verify import policy
from app.llm.gateway import Gateway
from app.llm.prompts import load_prompt

Class = Literal[
    "PROMISE",
    "PART_PAYMENT",
    "DISPUTE",
    "STATEMENT_REQUEST",
    "PAYMENT_CONFIRMATION",
    "NO_INTENT_UNCLEAR",
    "OTHER_NOISE",
]
CLASSES: set[str] = {
    "PROMISE",
    "PART_PAYMENT",
    "DISPUTE",
    "STATEMENT_REQUEST",
    "PAYMENT_CONFIRMATION",
    "NO_INTENT_UNCLEAR",
    "OTHER_NOISE",
}


DISPUTE_KINDS = (
    ("quantity mismatch", re.compile(r"\b(units?|qty|quantity|pieces|pcs|received only|short)\b", re.I)),
    ("price mismatch", re.compile(r"\b(rate|price|priced|agreed \d)", re.I)),
    ("damaged goods", re.compile(r"\b(damaged|broken|defective)\b", re.I)),
    ("not delivered", re.compile(r"\b(never received|not received|not delivered|no delivery)\b", re.I)),
)


def dispute_reason(reply: str) -> str:
    """'<category>: <reply text>' so a collector can scan disputes by kind; rules, not the model."""
    kind = next((k for k, rx in DISPUTE_KINDS if rx.search(reply)), "other")
    return f"{kind}: {reply.strip()}"[:200]


def as_class(value: str) -> Class:
    return cast(Class, value) if value in CLASSES else "NO_INTENT_UNCLEAR"


PAST_CLASSES = {"PART_PAYMENT", "PAYMENT_CONFIRMATION"}
INVOICE = re.compile(r"\bINV-\d+\b")
DATE_PHRASES = [
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s*\d{4})?",
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?",
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    r"\b(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(?:tomorrow|yesterday|yday|today)\b",
    r"\b\d{1,2}\s+days?\b",
    r"\b(?:on\s+)?\d{1,2}(?:st|nd|rd|th)\b",
    r"\bnow\b",
]


@dataclass(frozen=True)
class Classification:
    klass: Class
    amount_paise: int | None
    stated_date: date | None
    invoice_refs: tuple[str, ...]
    confidence: float
    injection_suspected: bool
    source: Literal["llm", "rules"]
    note: str = ""


def injection_suspected(text_: str) -> bool:
    text_ = unicodedata.normalize("NFKC", text_)  # fullwidth and compatibility forms, as the policy promises
    return any(re.search(p, text_, re.IGNORECASE) for p in policy().injection)


def date_phrases(reply: str) -> set[str]:
    """Whole date phrases in the reply; where patterns overlap ("3rd Oct", "3rd") only the longest counts."""
    found = sorted(
        (m for p in DATE_PHRASES for m in re.finditer(p, reply, re.IGNORECASE)),
        key=lambda m: m.end() - m.start(),
        reverse=True,
    )
    out: list[re.Match[str]] = []
    for m in found:
        if all(m.end() <= o.start() or m.start() >= o.end() for o in out):
            out.append(m)
    return {m.group().strip().lower() for m in out}


def _amount(amount_text: str | None, reply: str) -> int | None:
    """Code parses the amount; a figure that is not in the customer's own words is dropped."""
    if not amount_text:
        return None
    wanted = amount_text.strip().lower()
    # the model's text must be a whole amount the customer wrote, not a piece of one ("₹5" in "₹50,000")
    return next((s.paise for s in parse_amounts(reply) if s.raw.strip().lower() == wanted), None)


def _date(date_text: str | None, reply: str, today: date, klass: str) -> date | None:
    if not date_text:
        return None
    # A date that ends a sentence is captured with its full stop ("5 oct."); the model quotes it without one.
    wanted = date_text.strip().lower().rstrip(".")
    if wanted not in {p.rstrip(".") for p in date_phrases(reply)}:
        return None  # not a date phrase the customer wrote
    try:
        return resolve_date(date_text, today, "past" if klass in PAST_CLASSES else "future")
    except DateInvalidError:
        return None


def rules(reply: str) -> tuple[str, float]:
    """Deterministic fallback. Order matters: the most specific intent wins."""
    t = reply.lower()
    if injection_suspected(reply):
        return "OTHER_NOISE", 0.9
    if re.search(
        r"out of office|happy (diwali|dussehra|new year|holi)|greetings|thank you for your email", t
    ):
        return "OTHER_NOISE", 0.8
    if re.search(
        r"wrong|damaged|never received|not received|short supply|returning|billed for|charged twice|"
        r"quality issue|credit note|revised bill|agreed .* not|complaint",
        t,
    ):
        return "DISPUTE", 0.8
    if re.search(r"statement|ledger|\bsoa\b|copies of|reconcil", t):
        return "STATEMENT_REQUEST", 0.8
    if re.search(r"part payment|(paid|transferred|sending|done)\b.*\b(balance|bal|rest|remaining)", t):
        return "PART_PAYMENT", 0.8
    if re.search(r"already paid|paid in full|cleared|credited|payment done|pymt done|\bpaid\b", t):
        return "PAYMENT_CONFIRMATION", 0.8
    if re.search(
        r"(will|can|shall|'ll|will be)\s+(pay|clear|transfer|release|deposit|do|be made|be deposited)|"
        r"give \d+ days|will pay|pay .* on|payment of .* will",
        t,
    ):
        return "PROMISE", 0.8
    return "NO_INTENT_UNCLEAR", 0.5


def _first(patterns: list[str], text_: str) -> str | None:
    for p in patterns:
        if m := re.search(p, text_, re.IGNORECASE):
            return m.group().strip()
    return None


def classify(
    reply: str, today: date, open_invoices: list[str], gateway: Gateway | None, run_id: str | None = None
) -> Classification:
    suspected = injection_suspected(reply)
    note = ""
    if gateway is not None:
        try:
            prompt = load_prompt("classify_reply", 1)
            user = prompt.render(
                reply_text=reply, today=f"{today:%d %b %Y}", open_invoices=", ".join(open_invoices) or "none"
            )
            result = gateway.complete(
                prompt.ref, [{"role": "user", "content": user}], max_tokens=prompt.max_tokens, run_id=run_id
            )
            raw = json.loads(re.sub(r"^```(?:json)?|```$", "", (result.text or "").strip(), flags=re.M))
            klass = str(raw.get("class", ""))
            if klass not in CLASSES:
                return Classification(
                    "NO_INTENT_UNCLEAR", None, None, (), 0.0, suspected, "llm", "CLASS_INVALID"
                )
            refs = tuple(r for r in raw.get("invoice_refs") or [] if isinstance(r, str) and r in reply)
            return Classification(
                as_class(klass),
                _amount(raw.get("amount_text"), reply),
                _date(raw.get("date_text"), reply, today, klass),
                refs,
                float(raw.get("confidence") or 0),
                suspected or bool(raw.get("injection_suspected")),
                "llm",
            )
        except Exception as e:  # noqa: BLE001  any model or parse failure falls back to the rules classifier
            note = f"model unavailable ({getattr(e, 'code', type(e).__name__)}); rules used"
    klass, conf = rules(reply)
    spans = parse_amounts(reply)
    dates = date_phrases(reply)
    if klass in ("PROMISE", "PART_PAYMENT", "PAYMENT_CONFIRMATION") and (
        len({s.paise for s in spans}) > 1 or len(dates) > 1
    ):
        conf, note = min(conf, 0.4), "MULTIPLE_FIGURES"  # which figure is the promise? a human decides
    amount = (
        spans[0].paise if spans and klass in ("PROMISE", "PART_PAYMENT", "PAYMENT_CONFIRMATION") else None
    )
    stated = (
        _date(_first(DATE_PHRASES, reply), reply, today, klass)
        if klass in ("PROMISE", "PART_PAYMENT", "PAYMENT_CONFIRMATION")
        else None
    )
    return Classification(
        as_class(klass),
        amount,
        stated,
        tuple(INVOICE.findall(reply)),
        conf,
        suspected,
        "rules",
        note,
    )
