"""Tone is chosen by code from history and ageing (REQ-031, LLD 3.3)."""

from typing import Literal

Tone = Literal["gentle", "firm", "final"]


def select_tone(oldest_days: int, missed_promises: int, reminded_recently: bool) -> Tone:
    if (missed_promises >= 1 and oldest_days > 30) or missed_promises >= 2 or oldest_days > 90:
        return "final"
    if oldest_days > 14 or missed_promises >= 1 or reminded_recently:
        return "firm"
    return "gentle"
