"""Web calls: Whisper writes spoken numbers as words; they become digits the amount parser reads."""

from app.channels.stt import words_to_digits
from app.core.money import parse_amounts


def test_spoken_amounts_become_money_the_parser_reads() -> None:
    cases = {
        "We can pay two lakh rupees this Friday.": 2_00_000,
        "two lakh fifty thousand by Monday": 2_50_000,
        "fifty thousand now": 50_000,
        "one crore twenty lakh": 1_20_00_000,
        "five hundred and twenty five thousand rupees": 5_25_000,
    }
    for said, rupees in cases.items():
        assert [s.paise for s in parse_amounts(words_to_digits(said))] == [rupees * 100], words_to_digits(
            said
        )


def test_other_words_and_small_numbers_stay_readable() -> None:
    assert words_to_digits("I have two invoices, not one.") == "I have 2 invoices, not 1."
    assert words_to_digits("Someone will call") == "Someone will call"
    assert words_to_digits("We paid 2 lakh already") == "We paid 2 lakh already"
