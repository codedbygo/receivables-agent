"""HACK-003 F2: which channel is next. Day 1 email, day 3 WhatsApp, day 7 voice, day 10 a person; preference,
feature flags and consent can change it, and every change is stated as a factor."""

from datetime import date

import pytest

from app.services.communication import ChannelPlan, choose

TODAY = date(2026, 10, 10)
ALL_ON = {"whatsapp": True, "sms": True, "voice": True}
CONSENT = {"email": True, "whatsapp": True, "sms": True, "voice": True}


def plan(
    first: date | None,
    *,
    preferred: str | None = None,
    enabled: dict[str, bool] = ALL_ON,
    consent: dict[str, bool] = CONSENT,
    replied: bool = False,
) -> ChannelPlan:
    return choose(
        first_contact=first,
        today=TODAY,
        preferred=preferred,
        enabled=enabled,
        consent=consent,
        replied=replied,
        last_channel="email" if first else None,
    )


@pytest.mark.parametrize(
    ("first", "expected"),
    [
        (None, "email"),
        (date(2026, 10, 10), "email"),  # day 1
        (date(2026, 10, 8), "whatsapp"),  # day 3
        (date(2026, 10, 4), "voice"),  # day 7
        (date(2026, 10, 1), "human"),  # day 10
    ],
)
def test_the_cadence(first: date | None, expected: str) -> None:
    assert plan(first).recommended_channel == expected


def test_a_messaging_preference_wins_over_the_messaging_step() -> None:
    p = plan(date(2026, 10, 8), preferred="sms")
    assert p.recommended_channel == "sms"
    assert any("prefers SMS" in f for f in p.factors)


def test_a_switched_off_or_unconsented_channel_falls_back_to_email() -> None:
    off = plan(date(2026, 10, 8), enabled={**ALL_ON, "whatsapp": False})
    assert off.recommended_channel == "email" and any("WhatsApp is switched off" in f for f in off.factors)
    no = plan(date(2026, 10, 8), consent={**CONSENT, "whatsapp": False})
    assert no.recommended_channel == "email" and any("not agreed" in f for f in no.factors)


def test_drafts_only_go_on_messaging_channels() -> None:
    assert (
        plan(date(2026, 10, 4)).draft_channel == "email"
    )  # voice day: the draft is email, the call is separate
    assert plan(date(2026, 10, 8)).draft_channel == "whatsapp"


def test_response_status_and_the_next_step() -> None:
    p = plan(date(2026, 10, 8))
    assert p.response_status == "no response"
    assert (p.next_step_channel, p.next_step_on) == ("voice", date(2026, 10, 14))
    assert plan(None).response_status == "never contacted"
    assert plan(date(2026, 10, 8), replied=True).response_status == "replied"
