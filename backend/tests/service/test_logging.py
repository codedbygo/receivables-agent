"""Logs are JSON lines with the request id and no customer text or addresses (US-01-014)."""

import json
import logging
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.main import create_app
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.services.demo import reset_demo, uid

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
SECRET_REPLY = "Please write to accounts@abc-private.example.in, we pay ₹3 lakh on October 5"


class Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def lines(engine: Engine) -> Iterator[list[str]]:
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    h = Lines()
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(logging.INFO)
    yield h.lines
    root.removeHandler(h)


def test_every_log_line_is_json_with_a_request_id_and_no_pii(lines: list[str]) -> None:
    # TC-0137 (AC-US-01-014-2)
    admin, collector = {"X-Demo-Role": "admin"}, {"X-Demo-Role": "collector"}
    with TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay"))) as api:
        api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=admin)
        [m] = api.get("/api/v1/messages", params={"filter[customer_id]": ABC}, headers=collector).json()[
            "data"
        ]
        api.post("/api/v1/replies", json={"message_id": m["id"], "body": SECRET_REPLY}, headers=collector)

    parsed = [json.loads(line) for line in lines]
    requests = [p for p in parsed if p.get("msg") == "request"]
    assert len(requests) >= 3 and all(p["request_id"].startswith("req_") for p in requests)
    assert all(p["method"] and p["path"].startswith("/api/v1/") and p["status"] for p in requests)
    joined = "\n".join(lines)
    assert "abc-private" not in joined and "3 lakh" not in joined
    assert "accounts@abc-distributors" not in joined  # the customer's stored address is never logged
