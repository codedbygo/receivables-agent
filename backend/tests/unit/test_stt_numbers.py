"""Web calls: Whisper writes spoken numbers as words; they become digits the amount parser reads."""

from typing import Any

import httpx
import pytest

from app.channels import stt
from app.channels.stt import words_to_digits
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.money import parse_amounts

DB = "postgresql+psycopg://x:x@localhost:1/x"


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


def test_without_the_voice_extra_a_clip_is_refused_and_the_app_still_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stt, "WhisperModel", None)
    stt._model.cache_clear()
    with pytest.raises(AppError) as e:
        stt.transcribe(b"webm", Settings(database_url=DB))
    assert e.value.code == ErrorCode.VOICE_PROVIDER


def test_with_a_groq_key_the_clip_goes_to_groq_and_numbers_come_back_as_digits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    def post(url: str, **kw: Any) -> httpx.Response:
        sent.update(url=url, **kw)
        return httpx.Response(200, json={"text": " We can pay two lakh this Friday. "})

    monkeypatch.setattr(stt.httpx, "post", post)
    said = stt.transcribe(
        b"clip", Settings(database_url=DB, groq_api_key="gsk_test"), "audio/webm;codecs=opus"
    )
    assert said == "We can pay 2,00,000 this Friday."
    assert sent["url"] == stt.GROQ_URL and sent["headers"]["Authorization"] == "Bearer gsk_test"
    assert sent["files"]["file"][0] == "speech.webm" and sent["data"]["language"] == "en"


def test_a_groq_failure_is_a_clear_error_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(database_url=DB, groq_api_key="gsk_test")
    monkeypatch.setattr(stt.httpx, "post", lambda url, **kw: httpx.Response(401, json={}))
    with pytest.raises(AppError) as e:
        stt.transcribe(b"clip", s)
    assert e.value.code == ErrorCode.VOICE_PROVIDER

    def down(url: str, **kw: Any) -> httpx.Response:
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(stt.httpx, "post", down)
    with pytest.raises(AppError):
        stt.transcribe(b"clip", s)
