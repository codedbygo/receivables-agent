"""The command-line entry points: seed, worker and evaluation (coverage pass of 2026-10-02)."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

import app.mcp.__main__ as mcp_main
import app.worker.__main__ as worker
from app.channels.email import ChannelError
from app.core.config import Settings, get_settings
from app.evaluation import harness
from app.seed.__main__ import main as seed_main
from app.services import approval
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).parents[2]


@pytest.fixture
def seeded(engine: Engine) -> Iterator[Engine]:
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    get_settings.cache_clear()
    yield engine
    get_settings.cache_clear()


def count(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_seed_if_empty_leaves_a_seeded_database_alone(
    seeded: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert seed_main(["--if-empty"]) == 0
    assert "already seeded" in capsys.readouterr().out


def test_seed_reset_puts_the_story_back(seeded: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    with seeded.begin() as c:
        c.execute(text("DELETE FROM timeline_events"))

    assert seed_main(["--reset"]) == 0
    assert "start of the ABC story" in capsys.readouterr().out
    assert count(seeded, "SELECT count(*) FROM customers") == 50


def test_seed_refuses_a_demo_date_the_seed_was_not_written_for(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_TODAY", "2027-01-01")

    assert seed_main(["--reset"]) == 1
    assert "DEMO_TODAY is 2027-01-01" in capsys.readouterr().err


def test_worker_handlers_run_the_daily_run_and_the_promise_check(seeded: Engine) -> None:
    table = worker.handlers(seeded, Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay"))

    table["daily_run"](seeded, {})
    table["promise_check"](seeded, {})

    assert count(seeded, "SELECT count(*) FROM agent_runs WHERE trigger = 'scheduled'") == 15


def test_worker_loop_survives_an_error_and_stops_on_sigterm(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def schedule(_engine: Engine, _now: object) -> None:
        calls.append("schedule")
        if len(calls) == 1:
            raise RuntimeError("database restarting")

    monkeypatch.setattr(worker, "schedule", schedule)
    monkeypatch.setattr(worker, "run_once", lambda _e, _t: None)
    monkeypatch.setattr(
        worker.time, "sleep", lambda _s: signal.raise_signal(signal.SIGTERM) if len(calls) > 1 else None
    )
    before = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    try:
        worker.main()
    finally:
        signal.signal(signal.SIGTERM, before[0])
        signal.signal(signal.SIGINT, before[1])

    assert calls == ["schedule", "schedule"]


def test_the_evaluation_entry_point_runs_offline() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "app.evaluation", "--offline"],
        cwd=BACKEND,
        env={**os.environ, "LLM_MODE": "replay"},
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    assert done.returncode == 0, done.stderr[-500:]
    assert "red team" in done.stdout


def test_an_unknown_scenario_setup_step_is_refused(seeded: Engine) -> None:
    with pytest.raises(ValueError, match="unknown setup step"):
        harness._setup(seeded, uid("customer", "ABC Distributors"), [{"bogus": 1}])


def test_a_failing_scenario_is_counted_and_listed(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_run_scenario", lambda _e, _b, sc: {"id": sc["id"], "ok": False})

    out = harness.eval_scenarios(seeded, Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay"))

    assert out["passed"] == 0 and len(out["failures"]) == out["total"] > 0


def test_seed_loads_an_empty_database(engine: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")
    get_settings.cache_clear()

    assert seed_main([]) == 0
    assert "50 customers, 300 invoices, 40 replies" in capsys.readouterr().out


def test_the_seed_module_runs_as_a_command(seeded: Engine) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "app.seed", "--if-empty"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 0 and "already seeded" in done.stdout


def test_the_worker_module_stops_cleanly_on_sigterm(seeded: Engine) -> None:
    before = count(seeded, "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.worker"], cwd=BACKEND, env={**os.environ, "LLM_MODE": "replay"}
    )
    for _ in range(200):  # until the worker holds its own database connection, i.e. it is in its loop
        now = count(seeded, "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        if isinstance(now, int) and isinstance(before, int) and now > before:
            break
        time.sleep(0.05)  # polling Postgres for the worker's connection, not a test assertion delay
    proc.send_signal(signal.SIGTERM)

    assert proc.wait(30) == 0


def test_the_send_handler_hands_the_message_to_the_worker(seeded: Engine) -> None:
    out = build_registry(seeded).invoke(
        "draft_message",
        {
            "customer_id": uid("customer", "ABC Distributors"),
            "kind": "reminder",
            "tone": "firm",
            "prose": "Dear ABC Distributors,\n\nThese invoices are past due:\n\n{{invoice_table}}\n\n"
            "Total outstanding: {{total}}\n\nCould you confirm a payment date?\n\nRegards,\nAccounts team",
        },
        ToolContext(actor="ai", source="agent"),
    )
    data = out["data"]
    assert isinstance(data, dict)
    with Session(bind=seeded) as s, s.begin():
        approval.approve(s, str(data["message_id"]), None, None)
    settings = Settings(database_url=os.environ["DATABASE_URL"], smtp_host="127.0.0.1", smtp_port=1)

    with pytest.raises(ChannelError):
        worker.handlers(seeded, settings)["send_message"](seeded, {"message_id": data["message_id"]})


def test_the_mcp_command_serves_http_with_the_bearer_check(monkeypatch: pytest.MonkeyPatch) -> None:
    served: list[object] = []
    monkeypatch.setattr(mcp_main.uvicorn, "run", lambda app, **kw: served.append((app, kw["port"])))
    monkeypatch.setattr(sys, "argv", ["app.mcp", "--port", "8123"])

    mcp_main.main()

    assert isinstance(served[0][0], mcp_main.BearerAuth) and served[0][1] == 8123
