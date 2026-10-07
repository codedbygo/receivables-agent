"""HACK-004 (CI coverage): the refusals and edge paths in services that no user flow reached."""

import os
from collections.abc import Callable, Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services import communication, disputes, executive, followups, memory, portal
from app.services.demo import reset_demo, uid
from app.services.priority import Factor, Priority

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
ANDHRA = uid("customer", "Andhra Industrial Supplies")
ANNAPURNA = uid("customer", "Annapurna Provision Stores")
NOBODY = uid("customer", "nobody")


@pytest.fixture
def s(engine: Engine) -> Iterator[Session]:
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    with Session(bind=engine) as session:
        yield session
        session.rollback()


def user(s: Session) -> str:
    return str(s.execute(text("SELECT id::text FROM users WHERE role = 'admin' LIMIT 1")).scalar_one())


def refused(act: Callable[[], object]) -> ErrorCode:
    with pytest.raises(AppError) as e:
        act()
    return e.value.code


def test_contact_preferences_refuse_an_unknown_channel_or_customer(s: Session) -> None:
    u = user(s)

    assert refused(lambda: communication.set_preferences(s, ABC, "fax", {}, u)) == ErrorCode.VALIDATION_ERROR
    assert refused(lambda: communication.set_preferences(s, NOBODY, None, {}, u)) == ErrorCode.NOT_FOUND


def test_a_dispute_move_refuses_an_unknown_dispute_or_team(s: Session) -> None:
    u = user(s)
    eastern = str(
        s.execute(
            text("""SELECT d.id::text FROM disputes d JOIN customers c ON c.id = d.customer_id
            WHERE c.name = 'Eastern Electricals'""")
        ).scalar_one()
    )

    assert (
        refused(lambda: disputes.transition(s, uid("dispute", "x"), "investigating", u))
        == ErrorCode.NOT_FOUND
    )
    assert (
        refused(lambda: disputes.transition(s, eastern, "investigating", u, team="legal"))
        == ErrorCode.VALIDATION_ERROR
    )


def test_a_high_balance_with_an_open_dispute_is_a_red_headline(s: Session) -> None:
    disputed = Factor(code="OPEN_DISPUTES", label="Open disputes", value="1", points=0, rule="context")
    ranked = [
        (
            ANDHRA,
            "Andhra Industrial Supplies",
            Priority(score=80, band="HIGH", reasons=[], factors=[disputed]),
        )
    ]

    [item] = executive.attention(s, ranked)

    assert (item.headline, item.severity) == ("Large outstanding balance and an open dispute", "red")


def test_a_broken_promise_gets_one_task_only(s: Session) -> None:
    promise = str(
        s.execute(
            text(f"SELECT promise_id::text FROM follow_up_tasks WHERE customer_id = '{ABC}' LIMIT 1")
        ).scalar_one()
    )

    assert followups.on_broken_promise(s, ABC, promise, "missed_promise") is None


def test_outside_manual_mode_a_task_with_nothing_to_chase_has_no_draft(s: Session) -> None:
    s.execute(text("UPDATE settings SET autonomy_mode = 'assisted' WHERE id = 1"))
    promise = str(
        s.execute(
            text(f"""INSERT INTO promises (customer_id, amount_paise, promised_date)
            VALUES ('{ANNAPURNA}', 100000, DATE '2026-09-20') RETURNING id::text""")
        ).scalar_one()
    )

    task = followups.on_broken_promise(s, ANNAPURNA, promise, "missed_promise")

    assert task is not None
    assert s.execute(text(f"SELECT message_id FROM follow_up_tasks WHERE id = '{task}'")).scalar() is None


def test_closing_a_task_needs_a_note_and_a_real_task(s: Session) -> None:
    u = user(s)
    task = str(
        s.execute(text(f"SELECT id::text FROM follow_up_tasks WHERE customer_id = '{ABC}'")).scalar_one()
    )

    assert refused(lambda: followups.close(s, task, "done", "  ", u)) == ErrorCode.REASON_REQUIRED
    assert refused(lambda: followups.close(s, uid("task", "x"), "done", "called", u)) == ErrorCode.NOT_FOUND


def test_an_empty_note_is_refused(s: Session) -> None:
    assert refused(lambda: memory.add_note(s, ABC, "   ", user(s))) == ErrorCode.VALIDATION_ERROR


def test_the_portal_refuses_an_empty_token_empty_text_and_a_far_date(s: Session) -> None:
    token = portal.create_link(s, ABC, user(s)).token
    far = date(2026, 9, 30) + timedelta(days=portal.PROMISE_WINDOW_DAYS + 1)

    assert refused(lambda: portal.view(s, "")) == ErrorCode.NOT_FOUND
    assert refused(lambda: portal.help_request(s, token, "   ")) == ErrorCode.VALIDATION_ERROR
    assert refused(lambda: portal.promise(s, token, 100000, far)) == ErrorCode.VALIDATION_ERROR
