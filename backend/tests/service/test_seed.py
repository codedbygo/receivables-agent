"""US-01-003, US-01-005: deterministic seed and reset to the start of the ABC story."""

import os
import threading
from datetime import date

import pytest
from sqlalchemy import Engine, text

from app.core.clock import today
from app.core.config import Settings
from app.services.demo import reset_demo, seed

pytestmark = pytest.mark.integration
S = Settings()


@pytest.fixture
def seeded(engine: Engine) -> Engine:
    reset_demo(engine, S)
    return engine


def q(engine: Engine, sql: str) -> list[tuple[object, ...]]:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(sql))]


def one(engine: Engine, sql: str) -> object:
    return q(engine, sql)[0][0]


BUSINESS_DUMP = """
SELECT 'c', id::text, name, email, segment FROM customers UNION ALL
SELECT 'i', id::text, number, status, amount_paise::text FROM invoices UNION ALL
SELECT 'p', id::text, customer_id::text, amount_paise::text, received_on::text FROM payments UNION ALL
SELECT 'r', id::text, customer_id::text, body, classification FROM replies UNION ALL
SELECT 'pr', id::text, customer_id::text, amount_paise::text, status FROM promises
ORDER BY 1, 2
"""


# TC-0226 (AC-US-01-003-1)
def test_counts(seeded: Engine) -> None:
    assert one(seeded, "SELECT count(*) FROM customers") == 50
    assert one(seeded, "SELECT count(*) FROM invoices") == 300
    assert one(seeded, "SELECT count(*) FROM replies") == 40


# TC-0226 (AC-US-01-003-1)
def test_seed_is_identical_on_every_run(seeded: Engine) -> None:
    first = q(seeded, BUSINESS_DUMP)
    reset_demo(seeded, S)
    assert q(seeded, BUSINESS_DUMP) == first


# TC-0227 (AC-US-01-003-2), TC-0229 (AC-US-01-003-4)
def test_amounts_names_and_domains(seeded: Engine) -> None:
    lo, hi = q(seeded, "SELECT min(amount_paise), max(amount_paise) FROM invoices")[0]
    assert isinstance(lo, int) and isinstance(hi, int)
    assert 1_500_000 <= lo and hi <= 250_000_000
    names = {r[0] for r in q(seeded, "SELECT name FROM customers")}
    assert {
        "ABC Distributors",
        "Sri Lakshmi Industries",
        "Kumar Electricals",
        "Andhra Industrial Supplies",
        "Metro Wholesale",
    } <= names
    assert one(seeded, "SELECT count(*) FROM customers WHERE email NOT LIKE '%example.in'") == 0


# TC-0228 (AC-US-01-003-3)
def test_every_profile_has_at_least_two_customers(seeded: Engine) -> None:
    profiles = {
        "hugely overdue": "SELECT count(DISTINCT customer_id) FROM invoices WHERE status <> 'paid' AND due_date < DATE '2026-09-30' - 90",
        "recently overdue": "SELECT count(DISTINCT customer_id) FROM invoices WHERE status <> 'paid' AND due_date BETWEEN DATE '2026-09-30' - 30 AND DATE '2026-09-29'",
        "fully paid": "SELECT count(*) FROM (SELECT customer_id FROM invoices GROUP BY 1 HAVING bool_and(status = 'paid')) t",
        "partially paid": "SELECT count(DISTINCT customer_id) FROM invoices WHERE status = 'partially_paid'",
        "disputed": "SELECT count(DISTINCT customer_id) FROM disputes WHERE status = 'open'",
        "broken promise": "SELECT count(DISTINCT customer_id) FROM promises WHERE status = 'missed'",
        "clean": "SELECT count(*) FROM (SELECT customer_id FROM invoices GROUP BY 1 HAVING bool_and(status = 'paid' OR due_date >= DATE '2026-09-30')) t",
    }
    counts = {k: one(seeded, sql) for k, sql in profiles.items()}
    assert all(isinstance(v, int) and v >= 2 for v in counts.values()), counts


# TC-0233 (AC-US-01-005-2)
def test_abc_is_at_the_start_of_the_story(seeded: Engine) -> None:
    abc = "(SELECT id FROM customers WHERE name = 'ABC Distributors')"
    open_invoices = q(
        seeded,
        f"SELECT number, amount_paise, due_date FROM invoices WHERE customer_id = {abc} AND status = 'unpaid' ORDER BY number",
    )
    assert open_invoices == [
        ("INV-1021", 40_000_000, date(2026, 9, 11)),
        ("INV-1034", 20_000_000, date(2026, 9, 18)),
        ("INV-1047", 15_000_000, date(2026, 9, 25)),
    ]
    assert one(seeded, f"SELECT count(*) FROM invoices WHERE customer_id = {abc} AND status = 'paid'") == 1
    assert (
        one(seeded, f"SELECT sum(remaining_paise) FROM invoice_balances WHERE customer_id = {abc}")
        == 75_000_000
    )
    assert one(seeded, f"SELECT count(*) FROM promises WHERE customer_id = {abc} AND status = 'missed'") == 1
    assert one(seeded, f"SELECT count(*) FROM messages WHERE customer_id = {abc}") == 0
    assert one(seeded, f"SELECT count(*) FROM disputes WHERE customer_id = {abc}") == 0


def test_invoice_status_agrees_with_the_ledger(seeded: Engine) -> None:
    bad = q(
        seeded,
        """
        SELECT i.number, i.status, b.paid_paise, b.remaining_paise FROM invoices i JOIN invoice_balances b ON b.invoice_id = i.id
        WHERE i.status <> 'disputed' AND i.status <> CASE WHEN b.remaining_paise = 0 THEN 'paid'
              WHEN b.paid_paise > 0 THEN 'partially_paid' ELSE 'unpaid' END""",
    )
    assert bad == []


# TC-0230 (AC-US-01-004-1)
def test_settings_row_and_clock(seeded: Engine) -> None:
    with seeded.connect() as c:
        from sqlalchemy.orm import Session

        with Session(bind=c) as s:
            assert today(s) == date(2026, 9, 30)
    assert one(seeded, "SELECT sending_enabled FROM settings") is True


# TC-0232 (AC-US-01-005-1)
def test_reset_keeps_users_and_llm_spend(seeded: Engine) -> None:
    before = one(seeded, "SELECT COALESCE(sum(cost_micro_usd), 0) FROM llm_calls")
    with seeded.begin() as c:
        c.execute(
            text("""INSERT INTO llm_calls (prompt_name, prompt_version, model, mode, replay_key, input_tokens,
                          output_tokens, cost_micro_usd) VALUES ('t', 1, 'm', 'live', 'k', 10, 10, 4500)""")
        )
        c.execute(text("UPDATE settings SET demo_today = DATE '2026-10-05', sending_enabled = false"))
    users = one(seeded, "SELECT count(*) FROM users")
    reset_demo(seeded, S)
    assert one(seeded, "SELECT sum(cost_micro_usd) FROM llm_calls") == before + 4500  # type: ignore[operator]
    assert one(seeded, "SELECT count(*) FROM users") == users == 3
    assert q(seeded, "SELECT demo_today, sending_enabled FROM settings") == [(date(2026, 9, 30), True)]


def test_seed_on_a_seeded_database_is_refused(seeded: Engine) -> None:
    with pytest.raises(RuntimeError, match="already seeded"):
        seed(seeded, S)


def test_reset_waits_for_a_concurrent_draft_instead_of_failing(seeded: Engine) -> None:
    # HACK-001: Reset during a worker's daily run failed with fk_message_invoices_invoice_id.
    worker = seeded.connect()
    tx = worker.begin()
    worker.execute(
        text("""INSERT INTO messages (id, customer_id, kind, channel, tone, status, subject, body)
        SELECT gen_random_uuid(), customer_id, 'reminder', 'email', 'firm', 'pending_approval', 's', 'b'
        FROM invoices WHERE number = 'INV-1021'""")
    )
    worker.execute(
        text("""INSERT INTO message_invoices (message_id, invoice_id)
        SELECT m.id, i.id FROM messages m JOIN invoices i ON i.number = 'INV-1021' LIMIT 1""")
    )
    errors: list[BaseException] = []
    t = threading.Thread(target=lambda: _reset(seeded, errors))
    t.start()
    _wait_until_blocked(seeded)

    tx.commit()
    worker.close()
    t.join(timeout=60)

    assert errors == []
    assert q(seeded, "SELECT count(*) FROM message_invoices") == [(0,)]
    assert q(seeded, "SELECT count(*) FROM customers") == [(50,)]


def _reset(engine: Engine, errors: list[BaseException]) -> None:
    try:
        reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    except BaseException as e:  # noqa: BLE001  handed to the test thread to assert on
        errors.append(e)


def _wait_until_blocked(engine: Engine) -> None:
    """Poll until the reset is waiting on a lock held by the open draft transaction."""
    for _ in range(400):
        with engine.connect() as c:
            if c.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
            ).scalar():
                return
        threading.Event().wait(0.05)
    raise AssertionError("reset never waited on the draft's locks")


def test_reset_survives_a_deadlock_with_a_worker_mid_write(seeded: Engine) -> None:
    # e2e 2026-10-02: Admin reset during the worker's daily run failed 500 with DeadlockDetected.
    worker = seeded.connect()
    tx = worker.begin()
    worker.execute(
        text("""INSERT INTO messages (id, customer_id, kind, channel, tone, status, subject, body)
        SELECT gen_random_uuid(), customer_id, 'reminder', 'email', 'firm', 'pending_approval', 's', 'b'
        FROM invoices WHERE number = 'INV-1021'""")
    )
    errors: list[BaseException] = []
    t = threading.Thread(target=lambda: _reset(seeded, errors))
    t.start()
    _wait_until_blocked(seeded)

    # The worker now needs a table the reset already holds: a lock cycle. Postgres aborts the reset (it waited
    # first), which must retry once the worker's transaction ends instead of failing.
    worker.execute(
        text("""INSERT INTO message_invoices (message_id, invoice_id)
        SELECT m.id, i.id FROM messages m JOIN invoices i ON i.number = 'INV-1021' LIMIT 1""")
    )
    tx.commit()
    worker.close()
    t.join(timeout=60)

    assert errors == []
    assert q(seeded, "SELECT count(*) FROM messages") == [(0,)]
    assert q(seeded, "SELECT count(*) FROM customers") == [(50,)]
