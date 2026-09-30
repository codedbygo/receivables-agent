"""AC-US-01-004-2: business code reads dates only through app.core.clock."""

import re
from pathlib import Path

APP = Path(__file__).parents[2] / "app"
FORBIDDEN = re.compile(r"\b(date\.today\(|datetime\.now\(|datetime\.today\(|datetime\.utcnow\()")
ALLOWED = {APP / "core" / "clock.py"}


def test_no_wall_clock_for_business_dates() -> None:
    offenders = [
        f"{p.relative_to(APP)}:{n}"
        for p in APP.rglob("*.py")
        if p not in ALLOWED
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert offenders == [], f"use app.core.clock.today(): {offenders}"
