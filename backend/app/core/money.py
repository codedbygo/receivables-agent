"""Money: integer paise everywhere, INR text only at the edge (tenet 2, LLD 3.1)."""

import re
from dataclasses import dataclass
from decimal import Decimal

_UNITS = {
    "crores": 10**7,
    "crore": 10**7,
    "cr": 10**7,
    "lakhs": 10**5,
    "lakh": 10**5,
    "lacs": 10**5,
    "lac": 10**5,
    "l": 10**5,
    "thousand": 10**3,
    "k": 10**3,
}

# A money token: optional currency, a number (Indian or international grouping,
# or plain digits), optional decimals, optional unit, optional "/-".
_AMOUNT = re.compile(
    r"(?<![\w./-])"
    r"(?P<cur>₹|rs\.?|inr)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.(?P<dec>\d{1,2}))?"
    r"(?!\d|/\d)"
    r"(?:\s*(?P<unit>crores?|cr|lakhs?|lacs?|thousand|l|k)(?![a-z]))?"
    r"(?P<slash>\s*/-)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AmountSpan:
    start: int
    end: int
    paise: int
    raw: str


def parse_amounts(text: str) -> list[AmountSpan]:
    """Every money amount in text. A bare number is not money: it needs a
    currency, a unit, comma grouping or a trailing '/-'."""
    spans: list[AmountSpan] = []
    for m in _AMOUNT.finditer(text):
        num, unit = m.group("num"), (m.group("unit") or "").lower()
        if not (m.group("cur") or unit or "," in num or m.group("slash")):
            continue
        value = Decimal(num.replace(",", "") + "." + (m.group("dec") or "0")) * _UNITS.get(unit, 1) * 100
        if value != value.to_integral_value():
            continue  # sub-paise amounts are not money we can verify
        start = m.start("cur") if m.group("cur") else m.start("num")
        end = m.end("unit") if unit else (m.end("dec") if m.group("dec") else m.end("num"))
        spans.append(AmountSpan(start, end, int(value), text[start:end]))
    return spans


def format_inr(paise: int) -> str:
    """75_000_000 -> '₹7,50,000'; paise shown only when not zero."""
    if paise < 0:
        raise ValueError("money is never negative here")
    rupees, rem = divmod(paise, 100)
    digits = str(rupees)
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    body = ",".join([*groups, tail]) if groups else tail
    return f"₹{body}" + (f".{rem:02d}" if rem else "")
