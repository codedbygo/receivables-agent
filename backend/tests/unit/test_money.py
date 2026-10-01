import json
from pathlib import Path

import pytest

from app.core.money import format_inr, parse_amounts

V = json.loads((Path(__file__).parents[1] / "vectors" / "inr.json").read_text())


@pytest.mark.parametrize(("paise", "text"), V["format"])
# TC-0268 (AC-US-00-023-1)
def test_format_inr(paise: int, text: str) -> None:
    assert format_inr(paise) == text


@pytest.mark.parametrize(("text", "paise"), V["parse"])
# TC-0181 (AC-US-00-006-1)
def test_parse_single_amount(text: str, paise: int) -> None:
    assert [s.paise for s in parse_amounts(text)] == [paise]


@pytest.mark.parametrize("text", V["not_amounts"])
def test_not_amounts(text: str) -> None:
    assert parse_amounts(text) == []


def test_amount_in_a_draft_line() -> None:
    spans = parse_amounts("INV-1021 | ₹4,00,000 | due 11 Sep 2026")
    assert [(s.paise, s.raw) for s in spans] == [(40000000, "₹4,00,000")]


def test_two_amounts_in_a_reply() -> None:
    spans = parse_amounts("pymt of 2L done yday, bal 1.2L by 10th")
    assert [s.paise for s in spans] == [20000000, 12000000]


def test_negative_paise_rejected() -> None:
    with pytest.raises(ValueError):
        format_inr(-1)
