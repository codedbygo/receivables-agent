"""Deterministic priority (REQ-026 to REQ-028, LLD 3.2). Never touches the model."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.money import format_inr

Band = Literal["HIGH", "MEDIUM", "LOW"]
SEGMENT = {"enterprise": 1.0, "mid_market": 0.7, "sme": 0.4}


class PriorityInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    overdue_paise: int
    oldest_days: int
    overdue_count: int
    missed_promises: int
    open_disputes: int
    segment: str
    disputed_numbers: tuple[str, ...]


class Reason(BaseModel):
    code: str
    text: str


class Priority(BaseModel):
    score: int
    band: Band
    reasons: list[Reason]


def band(value: int) -> Band:
    return "HIGH" if value >= 60 else "MEDIUM" if value >= 35 else "LOW"  # Q-002


def score(p: PriorityInput) -> Priority:
    if p.overdue_paise == 0:
        return Priority(score=0, band="LOW", reasons=[])
    raw = (
        35 * min(p.overdue_paise / 50_000_000, 1)
        + 20 * min(p.oldest_days / 60, 1)
        + 20 * min(p.missed_promises / 2, 1)
        + 10 * min(p.overdue_count / 4, 1)
        + 10 * SEGMENT.get(p.segment, 0.4)
    )
    value = max(0, min(100, round(raw) - 5 * p.open_disputes))
    reasons: list[Reason] = []
    if p.overdue_paise >= 20_000_000:
        reasons.append(
            Reason(code="HIGH_OUTSTANDING", text=f"High outstanding ({format_inr(p.overdue_paise)})")
        )
    if p.oldest_days > 0:
        reasons.append(Reason(code="OLDEST_OVERDUE", text=f"Oldest invoice {p.oldest_days} days overdue"))
    if p.missed_promises:
        s = "" if p.missed_promises == 1 else "s"
        reasons.append(Reason(code="MISSED_PROMISES", text=f"{p.missed_promises} missed promise{s}"))
    if p.overdue_count >= 3:
        reasons.append(Reason(code="MANY_OVERDUE", text=f"{p.overdue_count} overdue invoices"))
    if p.segment == "enterprise":
        reasons.append(Reason(code="KEY_ACCOUNT", text="Key account"))
    for number in p.disputed_numbers:
        reasons.append(Reason(code="OPEN_DISPUTE", text=f"Open dispute on {number} (excluded)"))
    return Priority(score=value, band=band(value), reasons=reasons)


# Overdue figures exclude invoices with an open dispute (LLD 3.2).
_INPUTS = text("""
SELECT c.id, c.name, c.segment,
  COALESCE(SUM(b.remaining_paise) FILTER (WHERE i.due_date < :today AND i.status <> 'disputed'), 0)
    AS overdue,
  COALESCE(MAX(:today - i.due_date) FILTER (WHERE i.due_date < :today AND i.status <> 'disputed'
                                            AND b.remaining_paise > 0), 0) AS oldest,
  COUNT(*) FILTER (WHERE i.due_date < :today AND i.status <> 'disputed' AND b.remaining_paise > 0)
    AS n_overdue,
  (SELECT count(*) FROM promises p WHERE p.customer_id = c.id AND p.status = 'missed') AS missed,
  (SELECT array_agg(i2.number ORDER BY i2.number) FROM disputes d JOIN invoices i2 ON i2.id = d.invoice_id
    WHERE d.customer_id = c.id AND d.status = 'open') AS disputed
FROM customers c
LEFT JOIN invoices i ON i.customer_id = c.id
LEFT JOIN invoice_balances b ON b.invoice_id = i.id
WHERE (CAST(:cid AS uuid) IS NULL OR c.id = CAST(:cid AS uuid))
GROUP BY c.id
""")


def priorities(
    session: Session, today: date, customer_id: str | None = None
) -> list[tuple[str, str, Priority]]:
    """(customer id, name, priority) for every customer, highest first; ties by overdue then name."""
    rows = session.execute(_INPUTS, {"today": today, "cid": customer_id}).all()
    scored = []
    for r in rows:
        disputed = tuple(r.disputed or ())
        inp = PriorityInput(
            overdue_paise=r.overdue,
            oldest_days=r.oldest,
            overdue_count=r.n_overdue,
            missed_promises=r.missed,
            open_disputes=len(disputed),
            segment=r.segment,
            disputed_numbers=disputed,
        )
        scored.append((str(r.id), r.name, score(inp), r.overdue))
    scored.sort(key=lambda t: (-t[2].score, -t[3], t[1]))
    return [(cid, name, p) for cid, name, p, _ in scored]


def top(session: Session, today: date, limit: int = 15) -> list[tuple[str, str, Priority]]:
    """The daily run's selection (REQ-027): never a customer with nothing overdue."""
    return [t for t in priorities(session, today) if t[2].score > 0][:limit]
