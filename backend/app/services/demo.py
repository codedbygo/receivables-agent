"""Deterministic demo seed and reset (US-01-003, US-01-005, REQ-018 to REQ-025).

Everything derives from a fixed RNG and uuid5 keys, so two seeds of an empty
database hold identical business rows. The database seed stores 38 of the 40
labelled eval replies plus 2 history replies behind the missed promises: the two
ABC replies in the eval set are beats of the live demo story and would otherwise
sit on ABC's timeline before its first reminder. Evals read evals/replies.jsonl.
"""

import hashlib
import json
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from psycopg.errors import DeadlockDetected
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from app.agent.classify import dispute_category
from app.core.config import Settings
from app.services.disputes import team_for

DATA = Path(__file__).parents[1] / "seed" / "data"
SCHEMA = Path(__file__).parents[1] / "db" / "schema.sql"
NS = uuid.UUID("6b1f5c1e-9d6a-4f7e-8a51-3c2f0e7d9a10")
IST = timezone(timedelta(hours=5, minutes=30))
RNG_SEED = 20260930
TODAY = date(2026, 9, 30)  # the seed is written for the story's start date; DEMO_TODAY must match it
KEEP = {"users", "sessions", "llm_calls"}
LAKH = 100_000_00

CUSTOMERS: list[tuple[str, str, str]] = [  # name, segment, profile
    ("ABC Distributors", "mid_market", "fixture"),
    ("Kumar Electricals", "enterprise", "fixture"),
    ("Sri Lakshmi Industries", "mid_market", "fixture"),
    ("Metro Wholesale", "sme", "fixture"),
    ("Andhra Industrial Supplies", "enterprise", "fixture"),
    ("Ganesh Traders", "sme", "recent"),
    ("Balaji Agencies", "sme", "recent"),
    ("Coastal Hardware", "sme", "recent"),
    ("Deccan Polymers", "mid_market", "recent"),
    ("Shree Ram Textiles", "mid_market", "recent"),
    ("Vijaya Steel Corporation", "enterprise", "partial"),
    ("Krishna Pharma Distributors", "mid_market", "partial"),
    ("Nandi Foods", "sme", "partial"),
    ("Sai Packaging", "sme", "paid"),
    ("Pioneer Auto Parts", "mid_market", "partial"),
    ("Eastern Electricals", "mid_market", "disputed"),
    ("Mahalaxmi Enterprises", "sme", "disputed"),
    ("Royal Ceramics", "sme", "recent"),
    ("Surya Chemicals", "enterprise", "recent"),
    ("Tirupati Agro", "mid_market", "recent"),
    ("Godavari Cement Traders", "enterprise", "huge"),
    ("Nellore Rice Mills", "mid_market", "huge"),
    ("Vizag Marine Supplies", "mid_market", "clean"),
    ("Chennai Auto Components", "enterprise", "clean"),
    ("Hyderabad Pharma Links", "mid_market", "paid"),
    ("Mysore Silk House", "sme", "clean"),
    ("Pune Precision Tools", "enterprise", "recent"),
    ("Bharat Paints and Hardware", "sme", "partial"),
    ("Kaveri Agro Foods", "mid_market", "clean"),
    ("Lotus Electronics", "sme", "recent"),
    ("Annapurna Provision Stores", "sme", "paid"),
    ("Sahyadri Plastics", "mid_market", "huge"),
    ("Konark Furnishings", "sme", "clean"),
    ("Everest Industrial Gases", "enterprise", "recent"),
    ("Srinivasa Medical Distributors", "mid_market", "partial"),
    ("Jaipur Handloom Exports", "sme", "clean"),
    ("Malabar Spices Trading", "mid_market", "recent"),
    ("Narmada Pipes and Fittings", "enterprise", "huge"),
    ("Coromandel Fertilisers Agency", "mid_market", "recent"),
    ("Sunrise Stationers", "sme", "paid"),
    ("Hindustan Bearings Depot", "mid_market", "recent"),
    ("Western Ghats Coffee Traders", "sme", "clean"),
    ("Brahmaputra Tea Distributors", "mid_market", "recent"),
    ("Indus Textile Mills", "enterprise", "partial"),
    ("Venkateswara Hardware Mart", "sme", "recent"),
    ("Orient Kitchenware", "sme", "clean"),
    ("Pragati Office Solutions", "mid_market", "recent"),
    ("Saraswati Book Distributors", "sme", "paid"),
    ("Tata Nagar Steel Traders", "enterprise", "huge"),
    ("Ujjain Grain Merchants", "sme", "recent"),
]
REFERENCED = {  # invoices named in the labelled replies: number, customer, amount, due, status
    "INV-2040": ("Krishna Pharma Distributors", 180_000_00, date(2026, 9, 10), "unpaid"),
    "INV-2311": ("Eastern Electricals", 225_000_00, date(2026, 9, 5), "disputed"),
    "INV-2402": ("Mahalaxmi Enterprises", 64_000_00, date(2026, 8, 28), "disputed"),
    "INV-2519": ("Royal Ceramics", 112_000_00, date(2026, 9, 15), "unpaid"),
    "INV-2688": ("Tirupati Agro", 87_500_00, date(2026, 9, 20), "unpaid"),
    "INV-2873": ("Sai Packaging", 150_000_00, date(2026, 9, 14), "paid"),
}
EXTRA_PAID = {
    "ABC Distributors": 1,
    "Kumar Electricals": 2,
    "Sri Lakshmi Industries": 2,
    "Metro Wholesale": 1,
    "Andhra Industrial Supplies": 2,
}
HISTORY_REPLIES = [  # (customer, body, received, promise amount, promise date, status)
    (
        "ABC Distributors",
        "We will pay ₹2 lakh on 20 August.",
        date(2026, 8, 12),
        2 * LAKH,
        date(2026, 8, 20),
        "missed",
    ),
    (
        "Kumar Electricals",
        "Will clear 6.2L by 15th July.",
        date(2026, 7, 8),
        620_000_00,
        date(2026, 7, 15),
        "missed",
    ),
]
EXTRA_PROMISES = [("Kumar Electricals", 3 * LAKH, date(2026, 8, 25), date(2026, 8, 18))]  # missed, no reply
DEMO_USERS = [
    ("admin@example.in", "Asha (Admin)", "admin"),
    ("collector@example.in", "Priya (Collector)", "collector"),
    ("viewer@example.in", "Vikram (Viewer)", "viewer"),
]
DEMO_PASSWORD = "demo-password"  # noqa: S105  demo accounts only, printed in the README


def uid(*parts: object) -> str:
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def hash_password(password: str, salt: bytes | None = None) -> str:
    """scrypt from the standard library (LLD 11): 'scrypt$<salt hex>$<hash hex>'."""
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def ist(d: date, hour: int = 9) -> datetime:
    return datetime.combine(d, time(hour), IST)


@dataclass
class Plan:
    customers: list[dict[str, object]] = field(default_factory=list)
    invoices: list[dict[str, object]] = field(default_factory=list)
    payments: list[dict[str, object]] = field(default_factory=list)
    allocations: list[dict[str, object]] = field(default_factory=list)
    replies: list[dict[str, object]] = field(default_factory=list)
    promises: list[dict[str, object]] = field(default_factory=list)
    promise_invoices: list[dict[str, object]] = field(default_factory=list)
    disputes: list[dict[str, object]] = field(default_factory=list)
    escalations: list[dict[str, object]] = field(default_factory=list)
    follow_ups: list[dict[str, object]] = field(default_factory=list)
    timeline: list[dict[str, object]] = field(default_factory=list)


def build_plan() -> Plan:
    """Every row of the seed, computed without touching the database."""
    rng = random.Random(RNG_SEED)  # noqa: S311  deterministic demo data, not security
    plan = Plan()
    cid = {name: uid("customer", name) for name, _, _ in CUSTOMERS}
    fixtures = json.loads((DATA / "fixture_invoices.json").read_text(encoding="utf-8"))["invoices"]
    next_no = iter(range(3001, 4000))
    by_customer: dict[str, list[dict[str, object]]] = {n: [] for n in cid}

    for i, (name, segment, _) in enumerate(CUSTOMERS, 1):
        plan.customers.append(
            {
                "id": cid[name],
                "name": name,
                "email": f"accounts@{slug(name)}.example.in",
                "phone": f"+91-98000{i:05d}",
                "segment": segment,
                "credit_terms_days": 30 if segment != "enterprise" else 45,
            }
        )

    def invoice(name: str, number: str, amount: int, due: date, status: str) -> dict[str, object]:
        terms = 45 if dict((n, s) for n, s, _ in CUSTOMERS)[name] == "enterprise" else 30
        row = {
            "id": uid("invoice", number),
            "customer_id": cid[name],
            "number": number,
            "invoice_date": due - timedelta(days=terms),
            "due_date": due,
            "amount_paise": amount,
            "status": status,
        }
        plan.invoices.append(row)
        by_customer[name].append(row)
        return row

    def pay(inv: dict[str, object], amount: int, on: date) -> None:
        pid = uid("payment", inv["number"], amount)
        plan.payments.append(
            {
                "id": pid,
                "customer_id": inv["customer_id"],
                "amount_paise": amount,
                "received_on": on,
                "reference": f"NEFT {rng.randint(100000, 999999)}",
                "source": "manual",
                "match_status": "matched",
            }
        )
        plan.allocations.append(
            {"id": uid("allocation", pid), "payment_id": pid, "invoice_id": inv["id"], "amount_paise": amount}
        )
        plan.timeline.append(
            event(
                inv["customer_id"],
                on,
                "payment_received",
                "system",
                amount,
                "payment",
                pid,
                f"Payment received against {inv['number']}",
            )
        )

    def amount() -> int:
        return rng.randrange(15_000, 25_00_000, 500) * 100  # ₹15,000 to ₹25,00,000 (REQ-019)

    for name, rows in fixtures.items():
        for number, amt, _inv_date, due in rows:
            invoice(name, number, amt, date.fromisoformat(due), "unpaid")
    for number, (name, amt, due, status) in REFERENCED.items():
        inv = invoice(name, number, amt, due, "unpaid")
        if status == "paid":
            inv["status"] = "paid"
            pay(inv, amt, due + timedelta(days=6))
        elif status == "disputed":
            inv["status"] = "disputed"
    for name, n in EXTRA_PAID.items():
        for _ in range(n):
            due = TODAY - timedelta(days=rng.randint(60, 150))
            inv = invoice(name, f"INV-{next(next_no)}", amount(), due, "paid")
            pay(inv, int(inv["amount_paise"]), due + timedelta(days=rng.randint(0, 10)))  # type: ignore[call-overload]

    generated = [(n, p) for n, _, p in CUSTOMERS if p != "fixture"]
    remaining = 300 - len(plan.invoices)
    per = [remaining // len(generated)] * len(generated)
    for k in range(remaining - sum(per)):
        per[k] += 1
    for (name, profile), count in zip(generated, per, strict=True):
        has_open = any(i["status"] != "paid" for i in by_customer[name])
        for j in range(count):  # count is on top of any fixture or referenced invoice
            open_slot = j == 0 and not has_open
            if profile == "clean" or (profile == "recent" and not open_slot and rng.random() < 0.3):
                due = TODAY + timedelta(days=rng.randint(1, 45))
                status = "unpaid"
            elif profile == "huge" and open_slot:
                due, status = TODAY - timedelta(days=rng.randint(95, 160)), "unpaid"
            elif profile in ("recent", "partial", "disputed") and open_slot:
                due, status = TODAY - timedelta(days=rng.randint(3, 28)), "unpaid"
            else:
                due, status = TODAY - timedelta(days=rng.randint(35, 200)), "paid"
            inv = invoice(name, f"INV-{next(next_no)}", amount(), due, status)
            if status == "paid":
                pay(inv, int(inv["amount_paise"]), due + timedelta(days=rng.randint(0, 12)))  # type: ignore[call-overload]
            elif profile == "partial" and open_slot:
                part = int(inv["amount_paise"]) // 2 // 100 * 100  # type: ignore[call-overload]
                inv["status"] = "partially_paid"
                pay(inv, part, min(TODAY, due + timedelta(days=2)))
    assert len(plan.invoices) == 300, len(plan.invoices)

    for inv in plan.invoices:
        due = inv["due_date"]
        if isinstance(due, date) and due <= TODAY:
            plan.timeline.append(
                event(
                    inv["customer_id"],
                    due,
                    "invoice_due",
                    "system",
                    inv["amount_paise"],
                    "invoice",
                    inv["id"],
                    f"{inv['number']} due",
                )
            )

    _replies(plan, cid, by_customer)
    return plan


def _replies(plan: Plan, cid: dict[str, str], by_customer: dict[str, list[dict[str, object]]]) -> None:
    labelled = [
        json.loads(line) for line in (DATA / "replies.jsonl").read_text(encoding="utf-8").splitlines() if line
    ]
    for r in labelled:
        name = r["input"]["customer"]
        if name == "ABC Distributors":
            continue  # demo story beats, see module docstring
        received = date(2026, 9, 1) + timedelta(days=int(r["id"][2:]) % 28)
        row = {
            "id": uid("reply", r["id"]),
            "customer_id": cid[name],
            "body": r["input"]["text"],
            "received_at": ist(received, 11),
            "classification": None,
        }
        plan.replies.append(row)
        if r["expected"]["class"] == "DISPUTE" and r["expected"]["invoice_refs"]:
            number = r["expected"]["invoice_refs"][0]
            inv = next(
                (i for i in by_customer[name] if i["number"] == number and i["status"] == "disputed"), None
            )
            if inv:
                row["classification"] = "DISPUTE"
                did = uid("dispute", number)
                plan.disputes.append(
                    {
                        "id": did,
                        "customer_id": cid[name],
                        "invoice_id": inv["id"],
                        "reply_id": row["id"],
                        "reason": r["input"]["text"][:120],
                        "status": "assigned",  # routed by the same rule a live dispute gets (HACK-003 F7)
                        "category": dispute_category(r["input"]["text"]),
                        "assigned_team": team_for(dispute_category(r["input"]["text"])),
                    }
                )
                plan.escalations.append(
                    {
                        "id": uid("escalation", did),
                        "customer_id": cid[name],
                        "kind": "dispute",
                        "reason": f"{number} disputed",
                        "dispute_id": did,
                        "reply_id": row["id"],
                    }
                )
                plan.timeline.append(
                    event(
                        cid[name],
                        received,
                        "dispute_opened",
                        "customer",
                        None,
                        "dispute",
                        did,
                        f"Dispute on {number}",
                    )
                )
                plan.timeline.append(
                    event(
                        cid[name],
                        received,
                        "escalation_created",
                        "system",
                        None,
                        "escalation",
                        uid("escalation", did),
                        "Escalated to a collector",
                    )
                )
    for name, body, received, amt, on, status in HISTORY_REPLIES:
        rid = uid("history-reply", name, on)
        plan.replies.append(
            {
                "id": rid,
                "customer_id": cid[name],
                "body": body,
                "received_at": ist(received, 11),
                "classification": "PROMISE",
            }
        )
        _promise(plan, cid[name], by_customer[name], amt, on, received, status, rid)
    for name, amt, on, made in EXTRA_PROMISES:
        _promise(plan, cid[name], by_customer[name], amt, on, made, "missed", None)


def _promise(
    plan: Plan,
    customer: str,
    invoices: list[dict[str, object]],
    amt: int,
    on: date,
    made: date,
    status: str,
    reply_id: str | None,
) -> None:
    pid = uid("promise", customer, on)
    plan.promises.append(
        {
            "id": pid,
            "customer_id": customer,
            "reply_id": reply_id,
            "amount_paise": amt,
            "promised_date": on,
            "status": status,
            "resolved_at": ist(on + timedelta(days=1)),
        }
    )
    oldest = sorted((i for i in invoices if i["status"] != "paid"), key=lambda i: str(i["due_date"]))[:1]
    for inv in oldest:
        plan.promise_invoices.append({"promise_id": pid, "invoice_id": inv["id"]})
    plan.timeline.append(
        event(customer, made, "promise_logged", "customer", amt, "promise", pid, f"Promise for {on:%d %b %Y}")
    )
    plan.timeline.append(
        event(
            customer,
            on + timedelta(days=1),
            "promise_missed",
            "system",
            amt,
            "promise",
            pid,
            f"Promise for {on:%d %b %Y} missed",
        )
    )
    if status == "missed":  # the task the live path creates for a missed promise (HACK-003 F5)
        plan.follow_ups.append(
            {
                "id": uid("follow_up", pid),
                "customer_id": customer,
                "promise_id": pid,
                "kind": "missed_promise",
                "due_on": on + timedelta(days=1),
                "recommended_action": "Contact the customer today: the promised payment has not arrived.",
            }
        )
        plan.timeline.append(
            event(
                customer,
                on + timedelta(days=1),
                "followup_created",
                "system",
                None,
                "follow_up",
                uid("follow_up", pid),
                "Follow-up task: contact the customer about the missed promise",
            )
        )


def event(
    customer: object,
    on: date,
    kind: str,
    actor: str,
    amount: object,
    ref_type: str,
    ref_id: object,
    summary: str,
) -> dict[str, object]:
    return {
        "id": uid("event", kind, ref_id, on),
        "customer_id": customer,
        "occurred_at": ist(on),
        "business_date": on,
        "kind": kind,
        "actor": actor,
        "amount_paise": amount,
        "ref_type": ref_type,
        "ref_id": ref_id,
        "summary": summary,
    }


def _tables() -> list[str]:
    """Tables in creation order: the initial schema, then each later migration's upgrade file (HACK-003)."""
    files = [SCHEMA, *sorted(SCHEMA.parent.glob("upgrade_*.sql"))]
    return [
        t
        for f in files
        for t in re.findall(r"^CREATE TABLE (\w+) \(", f.read_text(encoding="utf-8"), flags=re.M)
    ]


def _insert(conn: Connection, table: str, rows: list[dict[str, object]]) -> None:
    if rows:
        cols = list(rows[0])
        # table and column names are this module's constants, never input
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"  # noqa: S608
        conn.execute(text(sql), rows)


def _demo_extras(conn: Connection) -> None:
    """HACK-003 demo data: channel preferences, an internal note, and one past SIMULATED call. Safety Center counts
    are never seeded: they come only from real events."""
    collector = uid("user", "collector@example.in")
    kumar = uid("customer", "Kumar Electricals")
    conn.execute(
        text("UPDATE customers SET preferred_channel = 'whatsapp' WHERE id = CAST(:c AS uuid)"),
        {"c": uid("customer", "Metro Wholesale")},
    )
    conn.execute(
        text("UPDATE customers SET preferred_channel = 'sms' WHERE id = CAST(:c AS uuid)"),
        {"c": uid("customer", "Ganesh Traders")},
    )
    conn.execute(
        text("""INSERT INTO customer_notes (id, customer_id, author_id, body, created_at)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), CAST(:u AS uuid), :b, :t)"""),
        {
            "i": uid("note", "abc-1"),
            "c": uid("customer", "ABC Distributors"),
            "u": collector,
            "b": "Accounts head is Mr Rao; prefers email before 11 am. Payments usually clear on Fridays.",
            "t": ist(TODAY - timedelta(days=3), 10),
        },
    )
    call = uid("call", "kumar-1")
    on = TODAY - timedelta(days=6)
    summary = (
        "Call completed (SIMULATED). Outcome: unavailable. Next action: Call again on "
        f"{on + timedelta(days=1):%d %b %Y}."
    )
    conn.execute(
        text("""INSERT INTO calls (id, customer_id, requested_by, provider, simulated, status, state, outcome,
        provider_call_id, summary, follow_up_on, started_at, ended_at) VALUES (CAST(:i AS uuid), CAST(:c AS uuid),
        CAST(:u AS uuid), 'simulated', true, 'completed', 'ended', 'unavailable', :p, :s, :f, :t, :t)"""),
        {
            "i": call,
            "c": kumar,
            "u": collector,
            "p": f"sim-call-{call}",
            "s": summary,
            "f": on + timedelta(days=1),
            "t": ist(on, 15),
        },
    )
    for seq, (who, said, intent) in enumerate(
        [
            (
                "ai",
                "Hello, this is the automated collections assistant calling from the accounts team. This call "
                "is not recorded. Could you let us know when we can expect payment?",
                None,
            ),
            ("customer", "He is not available, call later", "unavailable"),
            ("ai", "No problem. We will call back another time. Goodbye.", None),
        ],
        1,
    ):
        conn.execute(
            text("""INSERT INTO call_turns (call_id, seq, speaker, text, intent)
            VALUES (CAST(:k AS uuid), :n, :w, :t, :i)"""),
            {"k": call, "n": seq, "w": who, "t": said, "i": intent},
        )
    for kind, summary_ in (
        ("call_requested", "Call requested (SIMULATED provider: no phone rings)"),
        ("call_completed", summary),
    ):
        conn.execute(
            text("""INSERT INTO timeline_events (customer_id, occurred_at, business_date, kind, actor, ref_type,
            ref_id, summary) VALUES (CAST(:c AS uuid), :t, :d, :k, :a, 'call', CAST(:r AS uuid), :s)"""),
            {
                "c": kumar,
                "t": ist(on, 15),
                "d": on,
                "k": kind,
                "a": "human" if kind == "call_requested" else "ai",
                "r": call,
                "s": summary_,
            },
        )


def _settings(conn: Connection, s: Settings) -> None:
    conn.execute(
        text("""
        INSERT INTO settings (id, demo_today, sending_enabled, autonomy_mode, llm_budget_micro_usd,
                              feature_whatsapp, feature_voice, feature_payment_link, feature_trusted_mode,
                              feature_sms)
        VALUES (1, :d, :se, :am, :b, :fw, :fv, :fp, :ft, :fs)
        ON CONFLICT (id) DO UPDATE SET demo_today = EXCLUDED.demo_today,
          sending_enabled = EXCLUDED.sending_enabled, autonomy_mode = EXCLUDED.autonomy_mode,
          llm_budget_micro_usd = EXCLUDED.llm_budget_micro_usd,
          feature_whatsapp = EXCLUDED.feature_whatsapp, feature_voice = EXCLUDED.feature_voice,
          feature_payment_link = EXCLUDED.feature_payment_link,
          feature_trusted_mode = EXCLUDED.feature_trusted_mode, feature_sms = EXCLUDED.feature_sms,
          updated_at = now()"""),
        {
            "d": date.fromisoformat(s.demo_today),
            "se": s.sending_enabled,
            "am": s.autonomy_mode,
            "b": round(s.llm_budget_usd * 1_000_000),
            "fw": s.feature_whatsapp,
            "fv": s.feature_voice,
            "fp": s.feature_payment_link,
            "ft": s.feature_trusted_mode,
            "fs": s.feature_sms,
        },
    )


def is_seeded(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT count(*) FROM customers")).scalar_one())


def seed(engine: Engine, s: Settings) -> None:
    """Load the demo seed into an empty database (make seed)."""
    if date.fromisoformat(s.demo_today) != TODAY:
        raise RuntimeError(f"DEMO_TODAY is {s.demo_today}; the seed is written for {TODAY}")
    with engine.begin() as conn:
        if conn.execute(text("SELECT count(*) FROM customers")).scalar_one():
            raise RuntimeError("database already seeded; use make reset-demo")
        _load(conn, s)


def _load(conn: Connection, s: Settings) -> None:
    plan = build_plan()
    _settings(conn, s)
    for u_email, u_name, role in DEMO_USERS:
        conn.execute(
            text("""INSERT INTO users (id, email, display_name, role, password_hash)
                             VALUES (:id, :e, :n, :r, :h) ON CONFLICT DO NOTHING"""),
            {
                "id": uid("user", u_email),
                "e": u_email,
                "n": u_name,
                "r": role,
                "h": hash_password(DEMO_PASSWORD),
            },
        )
    for table, rows in [
        ("customers", plan.customers),
        ("invoices", plan.invoices),
        ("payments", plan.payments),
        ("payment_allocations", plan.allocations),
        ("replies", plan.replies),
        ("promises", plan.promises),
        ("promise_invoices", plan.promise_invoices),
        ("disputes", plan.disputes),
        ("escalations", plan.escalations),
        ("follow_up_tasks", plan.follow_ups),
        ("timeline_events", plan.timeline),
    ]:
        _insert(conn, table, rows)
    # Demo consent on every channel; a real customer's consent is recorded when given (HACK-003 F2).
    conn.execute(
        text("""UPDATE customers SET contact_consent =
        '{"email": true, "whatsapp": true, "sms": true, "voice": true}'::jsonb""")
    )
    _demo_extras(conn)


def reset_demo(engine: Engine, s: Settings) -> None:
    """Back to the start of the ABC story; users, sessions and LLM spend survive (AC-US-01-005-1)."""
    if date.fromisoformat(s.demo_today) != TODAY:
        raise RuntimeError(f"DEMO_TODAY is {s.demo_today}; the seed is written for {TODAY}")
    tables = [t for t in reversed(_tables()) if t not in KEEP]
    for attempt in range(3):
        try:
            _reset_once(engine, s, tables)
            return
        except OperationalError as e:
            # A worker writing while the reset takes its locks can close a lock cycle; Postgres aborts the
            # reset, and the retry waits for the worker's transaction to end instead.
            if not isinstance(e.orig, DeadlockDetected) or attempt == 2:
                raise


def _reset_once(engine: Engine, s: Settings, tables: list[str]) -> None:
    with engine.begin() as conn:
        # One transaction, every table locked first: a worker mid-draft finishes (or waits) instead of
        # committing rows between the deletes, and nobody sees the ledger half empty.
        conn.execute(text(f"LOCK TABLE {', '.join(tables)} IN ACCESS EXCLUSIVE MODE"))  # noqa: S608  schema names
        for table in tables:
            conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608  table names come from schema.sql
        _load(conn, s)
