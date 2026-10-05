"""REQ-026 to REQ-028, REQ-031: priority and tone are code, pinned to LLD 3.2 and 3.3."""

import pytest

from app.services.priority import PriorityInput, band, score
from app.services.tone import select_tone

ABC = PriorityInput(
    overdue_paise=75_000_000,
    oldest_days=19,
    overdue_count=3,
    missed_promises=1,
    open_disputes=0,
    segment="mid_market",
    disputed_numbers=(),
)


def test_abc_worked_example_is_66_high_with_reasons() -> None:
    p = score(ABC)

    assert (p.score, p.band) == (66, "HIGH")
    assert [r.text for r in p.reasons] == [
        "High outstanding (₹7,50,000)",
        "Oldest invoice 19 days overdue",
        "1 missed promise",
        "3 overdue invoices",
    ]


@pytest.mark.parametrize(("value", "expected"), [(60, "HIGH"), (59, "MEDIUM"), (35, "MEDIUM"), (34, "LOW")])
# TC-0167 (AC-US-00-002-4)
def test_band_edges(value: int, expected: str) -> None:
    assert band(value) == expected


@pytest.mark.parametrize(
    "change",
    [
        {"overdue_paise": 90_000_000},
        {"oldest_days": 45},
        {"missed_promises": 2},
        {"overdue_count": 4},
        {"segment": "enterprise"},
    ],
)
# TC-0164 (AC-US-00-002-1)
def test_each_factor_raises_the_score(change: dict[str, object]) -> None:
    base = PriorityInput(
        overdue_paise=10_000_000,
        oldest_days=10,
        overdue_count=1,
        missed_promises=0,
        open_disputes=0,
        segment="sme",
        disputed_numbers=(),
    )

    assert score(base.model_copy(update=change)).score > score(base).score


def test_open_dispute_lowers_the_score_and_says_so() -> None:
    disputed = ABC.model_copy(update={"open_disputes": 1, "disputed_numbers": ("INV-1047",)})

    p = score(disputed)

    assert p.score == score(ABC).score - 5
    assert p.reasons[-1].text == "Open dispute on INV-1047 (excluded)"


def test_nothing_overdue_scores_zero() -> None:
    p = score(
        PriorityInput(
            overdue_paise=0,
            oldest_days=0,
            overdue_count=0,
            missed_promises=0,
            open_disputes=0,
            segment="enterprise",
            disputed_numbers=(),
        )
    )

    assert (p.score, p.reasons) == (0, [])


@pytest.mark.parametrize(
    ("oldest_days", "missed", "reminded_recently", "tone"),
    [
        (5, 0, False, "gentle"),
        (20, 0, False, "firm"),
        (45, 1, False, "final"),
        (19, 1, False, "firm"),
        (5, 0, True, "firm"),
        (95, 0, False, "final"),
        (10, 2, False, "final"),
    ],
)
# TC-0172 (AC-US-01-001-3)
def test_tone(oldest_days: int, missed: int, reminded_recently: bool, tone: str) -> None:
    assert select_tone(oldest_days, missed, reminded_recently) == tone


# HACK-003 F4: every factor shows the points it added, and the points explain the score.
def test_abc_factors_show_points_that_add_up_to_the_score() -> None:
    p = score(ABC.model_copy(update={"no_response": True}))

    by_code = {f.code: f for f in p.factors}
    assert list(by_code) == [
        "OUTSTANDING",
        "OLDEST_OVERDUE",
        "MISSED_PROMISES",
        "OVERDUE_COUNT",
        "SEGMENT",
        "NO_ACTIVE_DISPUTE",
        "NO_RESPONSE",
    ]
    assert by_code["OUTSTANDING"].value == "₹7,50,000"
    assert by_code["OUTSTANDING"].points == 35.0
    assert by_code["NO_ACTIVE_DISPUTE"].points == 0
    assert by_code["NO_RESPONSE"].label == "No response to last reminder"
    assert abs(sum(f.points for f in p.factors) - p.score) < 0.5


def test_open_disputes_appear_as_a_deduction() -> None:
    p = score(ABC.model_copy(update={"open_disputes": 1, "disputed_numbers": ("INV-1047",)}))

    dispute = next(f for f in p.factors if f.code == "OPEN_DISPUTES")
    assert dispute.points == -5
    assert abs(sum(f.points for f in p.factors) - p.score) < 0.5


def test_nothing_overdue_has_no_factors() -> None:
    assert score(ABC.model_copy(update={"overdue_paise": 0})).factors == []
