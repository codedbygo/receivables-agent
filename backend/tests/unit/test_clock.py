"""Reply date resolution (LLD 3.1b); vectors from evals/replies.jsonl, today = Wed 30 Sep 2026."""

from datetime import date

import pytest

from app.core.clock import DateInvalidError, resolve_date

TODAY = date(2026, 9, 30)

FUTURE = [
    ("October 5", date(2026, 10, 5)),
    ("5th", date(2026, 10, 5)),
    ("15 October 2026", date(2026, 10, 15)),
    ("3rd Oct", date(2026, 10, 3)),
    ("next Friday", date(2026, 10, 2)),
    ("tomorrow", date(2026, 10, 1)),
    ("7/10/2026", date(2026, 10, 7)),
    ("10 days", date(2026, 10, 10)),
    ("12 October", date(2026, 10, 12)),
    ("Monday", date(2026, 10, 5)),
    ("10th", date(2026, 10, 10)),
    ("5 Oct", date(2026, 10, 5)),
]
PAST = [
    ("today", date(2026, 9, 30)),
    ("now", date(2026, 9, 30)),
    ("yesterday", date(2026, 9, 29)),
    ("yday", date(2026, 9, 29)),
    ("28 Sep", date(2026, 9, 28)),
    ("25/09/2026", date(2026, 9, 25)),
    ("20th", date(2026, 9, 20)),
    ("on 20th", date(2026, 9, 20)),
    ("26 September 2026", date(2026, 9, 26)),
]
NOT_A_DATE = ["last week", "end of Oct", "next month", "soon", "", "later"]


@pytest.mark.parametrize(("text", "expected"), FUTURE)
def test_future_dates(text: str, expected: date) -> None:
    assert resolve_date(text, TODAY, "future") == expected


@pytest.mark.parametrize(("text", "expected"), PAST)
def test_past_dates(text: str, expected: date) -> None:
    assert resolve_date(text, TODAY, "past") == expected


@pytest.mark.parametrize("text", NOT_A_DATE)
def test_not_a_single_date(text: str) -> None:
    assert resolve_date(text, TODAY, "future") is None


def test_year_rolls_over_in_december() -> None:
    assert resolve_date("October 5", date(2026, 12, 20), "future") == date(2027, 10, 5)


@pytest.mark.parametrize("text", ["31 Sep", "31/09/2026", "30 February"])
def test_impossible_dates_raise(text: str) -> None:
    with pytest.raises(DateInvalidError):
        resolve_date(text, TODAY, "future")
