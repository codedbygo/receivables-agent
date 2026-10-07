"""The post-deploy smoke checks run against the app in process (brief 9.3 step 6). The MCP and mail catcher
checks need the deployed stack; the MCP transports have their own tests (test_mcp_transports.py)."""

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app import smoke
from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).parents[2]


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    settings = Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    reset_demo(engine, settings)  # a deployed stack is seeded by its migrate step
    with TestClient(create_app(settings)) as c:
        yield c


def test_health_reset_and_dashboard_checks_pass_on_a_fresh_stack(
    api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.run(api, [smoke.health, smoke.reset, smoke.dashboard])
    assert capsys.readouterr().out.count("smoke: pass") == 3


def test_a_failing_check_is_reported_and_fails_the_run(
    api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_c: httpx.Client) -> str:
        raise AssertionError("readyz 503")

    assert not smoke.run(api, [smoke.health, broken])
    assert "smoke: FAIL  broken: readyz 503" in capsys.readouterr().out


def test_the_access_code_is_sent_when_one_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "code-1")

    assert smoke.headers() == {"Authorization": "Bearer code-1"}


def test_the_smoke_command_exits_1_when_the_stack_is_down() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "app.smoke"],
        cwd=BACKEND,
        env={**os.environ, "SMOKE_BASE_URL": "http://127.0.0.1:1", "MCP_URL": "http://127.0.0.1:1/mcp"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert done.returncode == 1 and "smoke: FAIL  health" in done.stdout


class Mailbox(http.server.BaseHTTPRequestHandler):
    """A stand-in for Mailpit's API: one message to ABC Distributors, or none."""

    messages: list[dict[str, object]] = []

    def do_GET(self) -> None:
        body = json.dumps({"messages": self.messages}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[Mailbox]]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Mailbox)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("MAILPIT_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("MAILPIT_UI_AUTH", "demo:pass")
    yield Mailbox
    server.shutdown()


def test_the_kill_switch_blocks_the_send_and_the_mail_arrives_after(
    api: TestClient, mailbox: type[Mailbox]
) -> None:
    mailbox.messages = [{"To": [{"Address": "accounts@abc-distributors.example.in"}]}]

    assert "email reached the mail catcher" in smoke.kill_switch_and_mail(api)
    assert api.get("/api/v1/admin/settings", headers=smoke.headers()).json()["sending_enabled"] is True


def test_a_mail_that_never_arrives_fails_the_check(
    api: TestClient, mailbox: type[Mailbox], monkeypatch: pytest.MonkeyPatch
) -> None:
    mailbox.messages = []
    monkeypatch.setattr(smoke.time, "sleep", lambda _s: None)

    with pytest.raises(AssertionError, match="no email to ABC Distributors"):
        smoke.kill_switch_and_mail(api)


def test_mcp_list_overdue_returns_the_ranked_overdue_from_the_running_server(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp", "--port", str(port)],
        cwd=BACKEND,
        env={**os.environ, "MCP_TOKEN": "t"},
    )
    try:
        for _ in range(100):  # until the server listens
            try:
                httpx.get(f"http://127.0.0.1:{port}/mcp", timeout=0.2)
                break
            except httpx.TransportError:
                time.sleep(0.1)  # waiting for a subprocess to bind, not a test assertion delay
        monkeypatch.setenv("MCP_URL", f"http://127.0.0.1:{port}/mcp")
        monkeypatch.setenv("MCP_TOKEN", "t")

        assert smoke.mcp_list_overdue(api) == "MCP list_overdue returns the top 7"
    finally:
        proc.terminate()
        proc.wait(10)


def test_an_unexpected_status_names_the_request() -> None:
    r = httpx.Response(503, text="down", request=httpx.Request("GET", "http://stack/api/v1/readyz"))

    with pytest.raises(AssertionError, match="GET /api/v1/readyz: 503 down"):
        smoke.ok(r)
