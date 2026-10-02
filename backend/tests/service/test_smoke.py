"""The post-deploy smoke checks run against the app in process (brief 9.3 step 6). The MCP and mail catcher
checks need the deployed stack; the MCP transports have their own tests (test_mcp_transports.py)."""

import os
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app import smoke
from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo

pytestmark = pytest.mark.integration


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
