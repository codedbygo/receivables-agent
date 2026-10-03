"""Jobs without a worker on Vercel (ADR-0015): a cron tick protected by CRON_SECRET runs due jobs inside a time
budget, and an approved message is sent in the same request when SEND_INLINE is on."""

import os
import smtplib
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.core.config import Settings
from app.services.demo import reset_demo, uid
from app.worker.jobs import enqueue
from app.worker.runner import handlers, tick

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
ADMIN, COLLECTOR = {"X-Demo-Role": "admin"}, {"X-Demo-Role": "collector"}


def settings(**kw: object) -> Settings:
    return Settings.model_validate({"database_url": os.environ["DATABASE_URL"], "llm_mode": "replay", **kw})


@pytest.fixture
def seeded(engine: Engine) -> Engine:
    reset_demo(engine, settings())
    return engine


def one(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def queue_promise_checks(engine: Engine, n: int) -> None:
    with engine.begin() as c:
        for i in range(n):
            enqueue(c, "promise_check", f"tick-{i}", {})


def test_the_cron_tick_refuses_a_missing_or_wrong_secret_and_an_unset_one(seeded: Engine) -> None:
    with TestClient(create_app(settings(cron_secret="s3cret"))) as api:
        missing = api.get("/api/v1/cron/tick")
        wrong = api.get("/api/v1/cron/tick", headers={"Authorization": "Bearer nope"})
    with TestClient(create_app(settings())) as api:
        unset = api.get("/api/v1/cron/tick", headers={"Authorization": "Bearer "})

    assert (missing.status_code, wrong.status_code, unset.status_code) == (401, 401, 401)


def test_the_cron_tick_runs_the_due_jobs(seeded: Engine) -> None:
    queue_promise_checks(seeded, 2)

    with TestClient(create_app(settings(cron_secret="s3cret"))) as api:
        r = api.get("/api/v1/cron/tick", headers={"Authorization": "Bearer s3cret"})

    assert r.status_code == 200 and r.json()["jobs_run"] >= 2
    assert one(seeded, "SELECT count(*) FROM jobs WHERE dedupe_key LIKE 'tick-%' AND status = 'done'") == 2


def test_a_tick_stops_at_its_time_budget(seeded: Engine) -> None:
    queue_promise_checks(seeded, 2)
    table = handlers(seeded, settings())

    assert tick(seeded, table, budget_s=0) == 0
    assert one(seeded, "SELECT count(*) FROM jobs WHERE dedupe_key LIKE 'tick-%' AND status = 'queued'") == 2


class InboxSMTP:
    sent: list[EmailMessage] = []

    def __init__(self, *_a: object, **_k: object) -> None:
        return None

    def __enter__(self) -> "InboxSMTP":
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def send_message(self, m: EmailMessage) -> None:
        self.sent.append(m)


@pytest.mark.parametrize(("inline", "status"), [(True, "sent"), (False, "approved")])
def test_an_approval_is_sent_in_the_same_request_only_when_inline_sending_is_on(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch, inline: bool, status: str
) -> None:
    InboxSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", InboxSMTP)
    with TestClient(create_app(settings(send_inline=inline))) as api:
        api.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=ADMIN)
        draft = api.get(
            "/api/v1/messages",
            params={"filter[customer_id]": ABC, "filter[status]": "pending_approval"},
            headers=COLLECTOR,
        ).json()["data"][0]

        approved = api.post(
            f"/api/v1/messages/{draft['id']}/approve",
            headers={**COLLECTOR, "If-Match": str(draft["version"])},
        )

    assert approved.status_code == 200
    assert one(seeded, f"SELECT status FROM messages WHERE id = '{draft['id']}'") == status
    assert len(InboxSMTP.sent) == (1 if inline else 0)
