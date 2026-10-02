"""Edge branches with no test until the coverage pass of 2026-10-02: unreal dates, sub-paise amounts, optional
prompt variables, a bad webhook timestamp, a database that does not answer, an unexpected error, the report."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import create_autospec

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.classify import classify
from app.api.main import create_app
from app.core.clock import DateInvalidError, resolve_date, today
from app.core.config import Settings
from app.core.db import ping
from app.core.errors import AppError
from app.core.paths import find_up
from app.evaluation import harness
from app.evaluation.harness import markdown, write
from app.llm.gateway import Gateway, PromptRef
from app.llm.prompts import Prompt
from app.services.auth import demo_user
from app.services.payments import sign, verify_signature


def test_29_february_without_a_year_is_refused() -> None:
    with pytest.raises(DateInvalidError, match="needs a year"):
        resolve_date("29 Feb", date(2026, 9, 30), "future")


def test_a_past_date_later_in_the_year_means_last_year() -> None:
    assert resolve_date("15 December", date(2026, 9, 30), "past") == date(2025, 12, 15)


def test_a_day_that_does_not_exist_this_month_moves_to_the_next() -> None:
    assert resolve_date("31st", date(2026, 9, 30), "future") == date(2026, 10, 31)


def test_a_future_day_in_december_rolls_into_january() -> None:
    assert resolve_date("5th", date(2026, 12, 20), "future") == date(2027, 1, 5)


def test_a_past_day_in_january_rolls_back_into_december() -> None:
    assert resolve_date("25th", date(2027, 1, 10), "past") == date(2026, 12, 25)


def test_a_day_that_exists_in_neither_month_is_refused() -> None:
    with pytest.raises(DateInvalidError, match="not a real date"):
        resolve_date("30th", date(2027, 1, 31), "future")


class _Result:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class _Session:
    def __init__(self, value: object) -> None:
        self.value = value

    def execute(self, *_args: object) -> _Result:
        return _Result(self.value)


def test_the_business_date_needs_the_settings_row() -> None:
    with pytest.raises(RuntimeError, match="settings row missing"):
        today(cast(Session, _Session(None)))
    with pytest.raises(RuntimeError, match="not a date"):
        today(cast(Session, _Session("2026-09-30")))


def test_a_missing_folder_is_named_in_the_error() -> None:
    with pytest.raises(FileNotFoundError, match="no no-such-folder/"):
        find_up("no-such-folder")


def test_an_optional_prompt_variable_renders_empty() -> None:
    prompt = Prompt(
        ref=PromptRef("t", 1),
        model="m",
        max_tokens=10,
        variables=({"name": "note", "required": False},),
        body="Note: [{{note}}]",
    )

    assert prompt.render() == "Note: []"


def test_a_webhook_timestamp_that_is_not_a_number_is_refused() -> None:
    body = b"{}"

    with pytest.raises(AppError) as e:
        verify_signature("s", "soon", sign("s", "soon", body), body)

    assert e.value.code == "REPLAY_WINDOW"


def test_readiness_is_false_when_the_database_does_not_answer() -> None:
    assert (
        ping(create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1}))
        is False
    )


def test_an_unexpected_error_is_a_500_with_the_request_id_and_no_internals() -> None:
    app = create_app(Settings(database_url="postgresql+psycopg://x:x@nowhere:1/x"))

    def boom() -> None:
        raise RuntimeError("secret internal detail")

    app.add_api_route("/api/v1/boom", boom)
    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/boom")

    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL" and "secret" not in r.text


def test_the_report_renders_every_section_and_is_written_to_both_files(tmp_path: Path) -> None:
    report = json.loads((find_up("evals") / "report.json").read_text(encoding="utf-8"))
    (tmp_path / "evals").mkdir()

    write(report, tmp_path)

    md = (tmp_path / "docs" / "evals" / "report.md").read_text(encoding="utf-8")
    assert md == markdown(report)
    assert "## Guardrails" in md and "## Trajectory scenarios" in md and "## Reply misses" in md
    assert (
        json.loads((tmp_path / "evals" / "report.json").read_text(encoding="utf-8"))["red_team"]
        == report["red_team"]
    )


def model(answer: str) -> Gateway:
    gateway = create_autospec(Gateway, instance=True)
    gateway.complete.return_value = SimpleNamespace(text=answer)
    return cast(Gateway, gateway)


def test_a_model_date_that_is_not_a_real_date_is_dropped() -> None:
    reply = "We will pay 3 lakh on 29 Feb."
    answer = '{"class": "PROMISE", "amount_text": "3 lakh", "date_text": "29 Feb", "confidence": 0.9}'

    c = classify(reply, date(2026, 9, 30), [], model(answer))

    assert (c.amount_paise, c.stated_date) == (30_000_000, None)


def test_a_class_the_product_does_not_know_is_unclear_and_flagged() -> None:
    c = classify("Hello", date(2026, 9, 30), [], model('{"class": "REFUND", "confidence": 0.99}'))

    assert (c.klass, c.confidence, c.note) == ("NO_INTENT_UNCLEAR", 0.0, "CLASS_INVALID")


def test_a_role_that_does_not_exist_signs_nobody_in() -> None:
    assert demo_user(cast(Session, object()), "root") is None


def test_failing_red_team_and_golden_drafts_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = {
        "redteam.yaml": [
            {"id": "r1", "customer": "ABC Distributors", "invoices": [], "text": "Hello", "expect_code": "X"}
        ],
        "golden.yaml": [{"id": "g1", "customer": "ABC Distributors", "invoices": [], "text": "Pay ₹1 now"}],
    }
    monkeypatch.setattr(harness, "_load_yaml", lambda name: cases[name])

    red, gold = harness.eval_drafts()

    assert red["failures"][0]["id"] == "r1" and gold["failures"][0]["id"] == "g1"


def test_a_failing_evaluation_names_each_failure_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = json.loads((find_up("evals") / "report.json").read_text(encoding="utf-8"))
    report["scenarios"] = {**report["scenarios"], "passed": 11, "rate": 11 / 12}
    written: list[object] = []
    monkeypatch.setattr(harness, "run", lambda offline, settings: report)
    monkeypatch.setattr(harness, "write", lambda r, root: written.append(root))

    status = harness.main([])

    assert status == 1 and written
    assert "eval: FAILED scenarios: 11/12" in capsys.readouterr().out


# Bug found 2026-10-02 by the coverage pass [HACK-001]: a date at the end of a sentence ("5 Oct.") was captured with
# its full stop, so the model's "5 Oct" did not match and the promise lost its date.
def test_a_date_at_the_end_of_a_sentence_matches_the_models_answer() -> None:
    answer = '{"class": "PROMISE", "amount_text": "3 lakh", "date_text": "5 Oct", "confidence": 0.9}'

    c = classify("We will pay 3 lakh on 5 Oct.", date(2026, 9, 30), [], model(answer))

    assert (c.source, c.stated_date) == ("llm", date(2026, 10, 5))
