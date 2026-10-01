"""The demo clock (tenet 5) and date phrases from replies (LLD 3.1b).

Business code reads the date only through today(); the value lives in the
settings row so api, mcp and worker agree and an admin can move it."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

Direction = Literal["future", "past"]
MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MON = r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s*(?P<year>\d{4}))?"
PATTERNS = [
    re.compile(rf"\b{_DAY}\s+{_MON}{_YEAR}\b"),  # 15 October 2026, 3rd Oct
    re.compile(rf"\b{_MON}\s+{_DAY}{_YEAR}\b"),  # October 5
    re.compile(r"\b(?P<day>\d{1,2})/(?P<num_mon>\d{1,2})/(?P<year>\d{4})\b"),  # 7/10/2026, day first
]
_DAY_ONLY = re.compile(r"^(?:on\s+)?(?:the\s+)?(?P<day>\d{1,2})(?:st|nd|rd|th)$")
_IN_DAYS = re.compile(r"^(?:in\s+)?(?P<n>\d{1,2})\s+days?$")


class DateInvalidError(ValueError):
    """A phrase that names a date that does not exist (31 Sep)."""


def today(session: Session) -> date:
    """The business date every computation uses (REQ-022)."""
    value = session.execute(text("SELECT demo_today FROM settings WHERE id = 1")).scalar_one_or_none()
    if value is None:
        raise RuntimeError("settings row missing: run make seed")
    if not isinstance(value, date):
        raise RuntimeError("settings.demo_today is not a date")
    return value


def _make(year: int, month: int, day: int, text_: str) -> date:
    try:
        return date(year, month, day)
    except ValueError as e:
        raise DateInvalidError(f"{text_!r} is not a real date") from e


def _nearest(month: int, day: int, today_: date, direction: Direction, text_: str) -> date:
    """Day and month without a year: the next (future) or last (past) occurrence."""
    candidate = _make(today_.year, month, day, text_) if not (month == 2 and day == 29) else None
    if candidate is None:
        raise DateInvalidError(f"{text_!r} needs a year")
    if direction == "future" and candidate < today_:
        return _make(today_.year + 1, month, day, text_)
    if direction == "past" and candidate > today_:
        return _make(today_.year - 1, month, day, text_)
    return candidate


def resolve_date(phrase: str, today_: date, direction: Direction) -> date | None:
    """A date phrase from a reply -> one date, or None when it names no single date."""
    t = " ".join(phrase.lower().split())
    if not t:
        return None
    if t in ("today", "now"):
        return today_
    if t == "tomorrow":
        return today_ + timedelta(days=1)
    if t in ("yesterday", "yday"):
        return today_ - timedelta(days=1)
    wd = re.fullmatch(
        r"(?:next\s+|this\s+|on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", t
    )
    if wd:
        ahead = (WEEKDAYS.index(wd.group(1)) - today_.weekday()) % 7 or 7
        return today_ + timedelta(days=ahead)
    if m := _IN_DAYS.match(t):
        return today_ + timedelta(days=int(m.group("n")))
    if m := _DAY_ONLY.match(t):
        day = int(m.group("day"))
        month, year = today_.month, today_.year
        for _ in range(2):  # this month, else the next (future) or previous (past) one
            try:
                d = date(year, month, day)
            except ValueError:
                d = None
            if d and ((direction == "future" and d >= today_) or (direction == "past" and d <= today_)):
                return d
            step = 1 if direction == "future" else -1
            month += step
            if month == 13:
                month, year = 1, year + 1
            if month == 0:
                month, year = 12, year - 1
        raise DateInvalidError(f"{phrase!r} is not a real date")
    for pat in PATTERNS:
        if m := pat.search(t):
            groups: dict[str, str | None] = m.groupdict()
            num_mon, mon = groups.get("num_mon"), groups.get("mon")
            month = int(num_mon) if num_mon else MONTHS[(mon or "")[:3]]
            day, yr = int(m.group("day")), groups.get("year")
            if yr:
                return _make(int(yr), month, day, phrase)
            return _nearest(month, day, today_, direction, phrase)
    # "30 February" style with a full month name the patterns caught above; anything else is vague
    return None


def wall_now() -> datetime:
    """Real time, for scheduling and audit only; never a business date (use today())."""
    return datetime.now(UTC)
