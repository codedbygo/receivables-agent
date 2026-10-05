"""Deterministic draft verification (REQ-048 to REQ-053, LLD 6.1). Runs on the final text after the
placeholders are filled; no model is involved. Returns a report of every token checked."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import cache

import yaml

from app.core.clock import PATTERNS, DateInvalidError, resolve_date
from app.core.money import format_inr, parse_amounts
from app.core.paths import find_up

INVOICE = re.compile(r"\bINV-\d+\b")
DATES = [re.compile(p.pattern, re.IGNORECASE) for p in PATTERNS]
# Payment details the ledger does not hold: a link, an email or UPI id (name@bank), an IFSC code or an
# account-length digit run, which may be split by single spaces or hyphens. Matched on NFKC text.
PAYMENT_DETAILS = re.compile(
    r"https?://\S+|\bwww\.\S+|\b[\w.+-]+@[a-z][\w.-]*\b|\b[A-Z]{4}0[A-Z0-9]{6}\b|(?<![\d-])(?:\d[ -]?){8,}\d\b",
    re.IGNORECASE,
)
SALUTATION = re.compile(r"^\s*(?:dear|hello|hi|to)\s+([^,\n]+)", re.IGNORECASE | re.MULTILINE)
PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}")


@dataclass(frozen=True)
class InvoiceFact:
    number: str
    customer: str
    amount_paise: int
    remaining_paise: int
    due: date


@dataclass(frozen=True)
class VerifyContext:
    customer: str
    cited: tuple[str, ...]
    invoices: dict[str, InvoiceFact]  # every invoice the verifier may meet, keyed by number
    customer_names: tuple[str, ...]
    today: date
    kind: str = "reminder"
    promise_amounts: tuple[int, ...] = ()
    promise_dates: tuple[date, ...] = ()
    disputed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    check: str
    token: str
    ok: bool
    code: str | None = None
    expected: str | None = None


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def codes(self) -> list[str]:
        return [c.code for c in self.checks if c.code]

    def add(self, check: str, token: str, code: str | None = None, expected: str | None = None) -> None:
        self.checks.append(Check(check, token, code is None, code, expected))


@dataclass(frozen=True)
class TrustedAllow:
    tones: tuple[str, ...]
    channels: tuple[str, ...]
    bands: tuple[str, ...]
    max_total_paise: int
    no_open_dispute: bool
    no_missed_promise: bool


@dataclass(frozen=True)
class Policy:
    tone: dict[str, list[str]]
    legal_allow: tuple[str, ...]
    injection: tuple[str, ...]
    trusted: TrustedAllow
    dispute_routing: dict[str, str]
    dispute_auto_resolve: tuple[str, ...]
    cadence: tuple[tuple[int, str], ...]


@cache
def policy() -> Policy:
    raw = yaml.safe_load((find_up("policy") / "guardrails.yaml").read_text(encoding="utf-8"))
    t = raw["trusted_mode_allow"]
    return Policy(
        tone={str(k): [str(x) for x in v] for k, v in raw["tone"].items()},
        legal_allow=tuple(str(x) for x in raw.get("legal_allow") or ()),
        injection=tuple(str(x) for x in raw["injection"]["patterns"]),
        trusted=TrustedAllow(
            tones=tuple(t["tone"]),
            channels=tuple(t["channel"]),
            bands=tuple(t["bands"]),
            max_total_paise=int(t["max_total_paise"]),
            no_open_dispute=bool(t["no_open_dispute"]),
            no_missed_promise=bool(t["no_missed_promise"]),
        ),
        dispute_routing={str(k): str(v) for k, v in (raw.get("dispute_routing") or {}).items()},
        dispute_auto_resolve=tuple(str(x) for x in raw.get("dispute_auto_resolve") or ()),
        cadence=tuple(sorted((int(c["day"]), str(c["channel"])) for c in raw.get("cadence") or [])),
    )


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _dates(line: str) -> list[re.Match[str]]:
    """Every date phrase the reply parser knows (ordinals, month first, optional year), without overlaps."""
    found = sorted((m for p in DATES for m in p.finditer(line)), key=lambda m: (m.start(), -m.end()))
    out: list[re.Match[str]] = []
    for m in found:
        if not out or m.start() >= out[-1].end():
            out.append(m)
    return out


def verify(text: str, ctx: VerifyContext, legal_allow: tuple[str, ...] | None = None) -> Report:
    report = Report()
    for m in PLACEHOLDER.finditer(text):
        report.add("placeholder", m.group(), "PLACEHOLDER_MISSING")
    cited = [ctx.invoices[n] for n in ctx.cited if n in ctx.invoices]
    total = sum(i.remaining_paise for i in cited)
    allowed = (
        {i.remaining_paise for i in cited} | {i.amount_paise for i in cited} | {total, *ctx.promise_amounts}
    )

    for line in text.splitlines():
        numbers = INVOICE.findall(line)
        for n in numbers:
            fact = ctx.invoices.get(n)
            if fact is None:
                report.add("invoice", n, "INVOICE_NOT_FOUND")
            elif fact.customer != ctx.customer:
                report.add("invoice", n, "INVOICE_WRONG_CUSTOMER")
            elif n in ctx.disputed and ctx.kind != "dispute_ack":
                report.add("invoice", n, "INVOICE_DISPUTED")
            else:
                report.add("invoice", n)
        own = ctx.invoices.get(numbers[0]) if len(numbers) == 1 else None
        own = own if own and own.customer == ctx.customer else None
        is_total = "total" in line.lower()
        for span in parse_amounts(line):
            if is_total:
                report.add(
                    "total", span.raw, None if span.paise == total else "TOTAL_MISMATCH", format_inr(total)
                )
            elif own is not None:
                ok = span.paise in (own.remaining_paise, own.amount_paise)
                report.add(
                    "amount", span.raw, None if ok else "AMOUNT_MISMATCH", format_inr(own.remaining_paise)
                )
            elif span.paise not in allowed:
                report.add("amount", span.raw, "INVENTED_AMOUNT")
            else:
                report.add("amount", span.raw)
        for m in _dates(line):
            try:
                d = resolve_date(m.group(), ctx.today, "past")
            except DateInvalidError:
                report.add("date", m.group(), "DATE_INVALID")
                continue
            if own is not None:
                report.add(
                    "date", m.group(), None if d == own.due else "DATE_MISMATCH", f"{own.due:%d %b %Y}"
                )
            elif d is not None and d > ctx.today and (d - ctx.today).days > 60:
                report.add("date", m.group(), "DATE_MISMATCH")
            elif (
                d is not None and d <= ctx.today and d not in {i.due for i in cited} | set(ctx.promise_dates)
            ):
                report.add("date", m.group(), "DATE_MISMATCH")
            else:
                report.add("date", m.group())

    for m in PAYMENT_DETAILS.finditer(unicodedata.normalize("NFKC", text)):
        report.add("payment_details", m.group(), "PAYMENT_DETAILS_UNVERIFIED")

    for m in SALUTATION.finditer(text):
        name = m.group(1).strip()
        report.add(
            "customer",
            name,
            None if _norm(name) == _norm(ctx.customer) else "CUSTOMER_MISMATCH",
            ctx.customer,
        )
    lowered = _norm(text)
    for other in ctx.customer_names:
        if other != ctx.customer and f" {_norm(other)} " in f" {lowered} ":
            report.add("customer", other, "CUSTOMER_MISMATCH", ctx.customer)

    p = policy()
    allow = tuple(a.lower() for a in (legal_allow if legal_allow is not None else p.legal_allow))
    scrubbed = text.lower()
    for phrase in allow:
        scrubbed = scrubbed.replace(phrase, " ")
    for category, patterns in p.tone.items():
        for pattern in patterns:
            if m2 := re.search(pattern, scrubbed, re.IGNORECASE):
                report.add("tone", m2.group(), "TONE_UNSAFE", category)
    return report
