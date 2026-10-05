"""Job handlers and the scheduler, shared by the long-running worker and the serverless cron tick (ADR-0015)."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, text

from app.agent.orchestrator import Orchestrator
from app.channels.email import EmailChannel, MessageChannel
from app.channels.messaging import messaging_channels
from app.core.config import Settings
from app.llm.gateway import Gateway
from app.services import approval
from app.services.priority import top
from app.tools.registry import build_registry
from app.worker.jobs import Handler, enqueue, run_once

IST = timezone(timedelta(hours=5, minutes=30))


def channels(settings: Settings) -> dict[str, MessageChannel]:
    return {
        "email": EmailChannel(
            settings.smtp_host,
            settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
            from_addr=settings.smtp_from,
            redirect_to=settings.email_redirect_to,
        ),
        **messaging_channels(settings),
    }


def send_handlers(settings: Settings) -> dict[str, Handler]:
    chans = channels(settings)
    return {"send_message": lambda e, p: approval.deliver(e, p["message_id"], chans)}


def handlers(engine: Engine, settings: Settings) -> dict[str, Handler]:
    orch = Orchestrator(engine, Gateway(settings, engine), build_registry(engine))

    def daily_run(e: Engine, _payload: dict[str, Any]) -> None:
        from sqlalchemy.orm import Session

        from app.core.clock import today

        with Session(bind=e) as s:
            selected = top(s, today(s), 15)
        for customer_id, _name, _p in selected:
            orch.run_collections(customer_id, "scheduled")

    def promise_check(e: Engine, _payload: dict[str, Any]) -> None:
        from app.services.payments import check_promises

        check_promises(e)

    return {"daily_run": daily_run, "promise_check": promise_check, **send_handlers(settings)}


def schedule(engine: Engine, now: datetime) -> None:
    """Once per demo date, from 09:00 IST wall time: the daily run and the promise check."""
    if now.astimezone(IST).hour < 9:
        return
    with engine.begin() as c:
        d = c.execute(text("SELECT demo_today FROM settings WHERE id = 1")).scalar()
        if d is not None:
            enqueue(c, "daily_run", str(d), {"run_date": str(d)})
            enqueue(c, "promise_check", str(d), {"date": str(d)})


def tick(engine: Engine, table: dict[str, Handler], budget_s: float) -> int:
    """Run due jobs until the queue is idle or the budget is spent; no new job starts after the deadline."""
    deadline, n = time.monotonic() + budget_s, 0
    while time.monotonic() < deadline and run_once(engine, table) is not None:
        n += 1
    return n
