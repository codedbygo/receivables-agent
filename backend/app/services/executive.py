"""CFO dashboard (HACK-003 F8): read-only SQL over the ledger. Every figure is computed here from rows;
definitions are returned with the numbers so the page can state them."""

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.money import format_inr
from app.services.priority import Factor, Priority, priorities

WEEKS = 8


class Kpis(BaseModel):
    total_receivables_paise: int
    overdue_paise: int
    collected_this_month_paise: int
    at_risk_paise: int
    promises_due_today_paise: int
    missed_promises_paise: int
    collection_rate_pct: int | None


class Point(BaseModel):
    label: str
    value: int


class Attention(BaseModel):
    customer_id: str
    customer_name: str
    severity: Literal["red", "amber"]
    score: int
    headline: str
    factors: list[Factor]


class Executive(BaseModel):
    today: date
    kpis: Kpis
    definitions: dict[str, str]
    ageing: list[Point]
    collections_by_week: list[Point]
    overdue_trend: list[Point]
    promise_outcomes: list[Point]
    risk_distribution: list[Point]
    collections_by_channel: list[Point]
    disputes_by_status: list[Point]
    expected_collections: list[Point]
    attention: list[Attention]


DEFINITIONS = {
    "total_receivables": "Remaining balance on every invoice.",
    "overdue": "Remaining balance on invoices past their due date.",
    "collected_this_month": "Matched payments received from the 1st of this month to today.",
    "at_risk": "Remaining balance on invoices that are disputed, belong to a HIGH priority customer, or belong "
    "to a customer with a missed promise.",
    "promises_due_today": "Pending promises dated today.",
    "missed_promises": "Promises whose date passed without full payment.",
    "collection_rate": "Collected this month divided by (collected this month plus overdue now).",
}


def collection_rate(collected: int, overdue: int) -> int | None:
    """Whole percent; None when there is nothing to collect and nothing collected."""
    total = collected + overdue
    return None if total == 0 else round(100 * collected / total)


def _points(session: Session, sql: str, params: dict[str, object]) -> list[Point]:
    return [Point(label=str(r.label), value=int(r.value)) for r in session.execute(text(sql), params)]


def executive(session: Session, today: date) -> Executive:
    ranked = priorities(session, today)
    high = [cid for cid, _, p in ranked if p.band == "HIGH"]
    p = {"d": today, "high": high}
    k = session.execute(
        text("""SELECT
        (SELECT COALESCE(SUM(remaining_paise), 0) FROM invoice_balances) AS total,
        (SELECT COALESCE(SUM(b.remaining_paise), 0) FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id
          WHERE i.due_date < :d) AS overdue,
        (SELECT COALESCE(SUM(amount_paise), 0) FROM payments WHERE match_status = 'matched'
          AND received_on BETWEEN date_trunc('month', CAST(:d AS date))::date AND :d) AS collected,
        (SELECT COALESCE(SUM(b.remaining_paise), 0) FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id
          WHERE b.remaining_paise > 0 AND (i.status = 'disputed' OR i.customer_id::text = ANY(CAST(:high AS text[]))
            OR EXISTS (SELECT 1 FROM promises m WHERE m.customer_id = i.customer_id AND m.status = 'missed')))
          AS at_risk,
        (SELECT COALESCE(SUM(amount_paise), 0) FROM promises WHERE status = 'pending' AND promised_date = :d)
          AS due_today,
        (SELECT COALESCE(SUM(amount_paise), 0) FROM promises WHERE status = 'missed') AS missed"""),
        p,
    ).one()
    kpis = Kpis(
        total_receivables_paise=k.total,
        overdue_paise=k.overdue,
        collected_this_month_paise=k.collected,
        at_risk_paise=k.at_risk,
        promises_due_today_paise=k.due_today,
        missed_promises_paise=k.missed,
        collection_rate_pct=collection_rate(int(k.collected), int(k.overdue)),
    )
    weeks = {"d": today, "n": WEEKS - 1}
    return Executive(
        today=today,
        kpis=kpis,
        definitions=DEFINITIONS,
        ageing=_points(
            session,
            """SELECT bucket AS label, COALESCE(SUM(rem), 0) AS value FROM (VALUES
              ('Not due', 0), ('0-30', 1), ('31-60', 2), ('61-90', 3), ('90+', 4)) AS b(bucket, ord)
            LEFT JOIN (SELECT b.remaining_paise AS rem, CASE WHEN i.due_date >= :d THEN 'Not due'
                WHEN :d - i.due_date <= 30 THEN '0-30' WHEN :d - i.due_date <= 60 THEN '31-60'
                WHEN :d - i.due_date <= 90 THEN '61-90' ELSE '90+' END AS bk
              FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id WHERE b.remaining_paise > 0) x
              ON x.bk = b.bucket GROUP BY bucket, ord ORDER BY ord""",
            p,
        ),
        collections_by_week=_points(
            session,
            """SELECT to_char(w, 'DD Mon') AS label, COALESCE(SUM(pay.amount_paise), 0) AS value
            FROM generate_series(CAST(:d AS date) - 7 * :n, CAST(:d AS date), interval '7 days') AS w
            LEFT JOIN payments pay ON pay.match_status = 'matched'
              AND pay.received_on > w::date - 7 AND pay.received_on <= w::date
            GROUP BY w ORDER BY w""",
            weeks,
        ),
        overdue_trend=_points(
            session,
            # Each week end: what was overdue then, counting only payments received by that day.
            """SELECT to_char(w, 'DD Mon') AS label, COALESCE(SUM(GREATEST(i.amount_paise - COALESCE(
                (SELECT SUM(a.amount_paise) FROM payment_allocations a JOIN payments pay ON pay.id = a.payment_id
                 WHERE a.invoice_id = i.id AND pay.received_on <= w::date), 0), 0)), 0) AS value
            FROM generate_series(CAST(:d AS date) - 7 * :n, CAST(:d AS date), interval '7 days') AS w
            LEFT JOIN invoices i ON i.due_date < w::date AND i.invoice_date <= w::date
            GROUP BY w ORDER BY w""",
            weeks,
        ),
        promise_outcomes=_points(
            session,
            """SELECT s AS label, (SELECT count(*) FROM promises WHERE status = s) AS value
            FROM unnest(ARRAY['fulfilled', 'partially_fulfilled', 'missed', 'pending']) AS s""",
            {},
        ),
        risk_distribution=[
            Point(label=b, value=sum(1 for _, _, pr in ranked if pr.band == b and pr.score > 0))
            for b in ("HIGH", "MEDIUM", "LOW")
        ],
        collections_by_channel=_points(
            session,
            # The channel of the last message sent to the customer before the payment arrived.
            """SELECT COALESCE(ch, 'no contact') AS label, SUM(amount_paise) AS value FROM (
              SELECT pay.amount_paise, (SELECT m.channel FROM messages m WHERE m.customer_id = pay.customer_id
                AND m.status = 'sent' AND m.sent_at <= pay.created_at ORDER BY m.sent_at DESC LIMIT 1) AS ch
              FROM payments pay WHERE pay.match_status = 'matched') x GROUP BY 1 ORDER BY 2 DESC""",
            {},
        ),
        disputes_by_status=_points(
            session,
            "SELECT status AS label, count(*) AS value FROM disputes GROUP BY status ORDER BY status",
            {},
        ),
        expected_collections=_points(
            session,
            """SELECT to_char(w, 'DD Mon') AS label, COALESCE(SUM(pr.amount_paise), 0) AS value
            FROM generate_series(CAST(:d AS date), CAST(:d AS date) + 21, interval '7 days') AS w
            LEFT JOIN promises pr ON pr.status = 'pending'
              AND pr.promised_date >= w::date AND pr.promised_date < w::date + 7
            GROUP BY w ORDER BY w""",
            p,
        ),
        attention=attention(session, ranked),
    )


def attention(session: Session, ranked: list[tuple[str, str, Priority]]) -> list[Attention]:
    """'What needs attention today': rules over the ledger, each item carrying the factors behind it."""
    missed = {
        r.customer_id: r.amount_paise
        for r in session.execute(
            text("""SELECT DISTINCT ON (customer_id) customer_id::text, amount_paise FROM promises
            WHERE status = 'missed' ORDER BY customer_id, promised_date DESC""")
        )
    }
    out: list[Attention] = []
    for cid, name, pr in ranked:
        if pr.score == 0:
            continue
        factors: list[Factor] = pr.factors
        oldest = next((f.value for f in factors if f.code == "OLDEST_OVERDUE"), "")
        disputed = any(f.code == "OPEN_DISPUTES" for f in factors)
        if cid in missed:
            headline, sev = f"Missed {format_inr(missed[cid])} promise", "red"
        elif pr.band == "HIGH" and disputed:
            headline, sev = "Large outstanding balance and an open dispute", "red"
        elif pr.band == "HIGH":
            headline, sev = f"High priority: oldest invoice {oldest} overdue", "red"
        else:
            headline, sev = f"Invoice overdue {oldest}", "amber"
        out.append(
            Attention(
                customer_id=cid,
                customer_name=name,
                severity=sev,
                score=pr.score,
                headline=headline,
                factors=factors,
            )
        )
    return out[:8]
