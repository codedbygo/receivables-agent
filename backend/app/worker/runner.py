"""Job handlers and the scheduler, shared by the long-running worker and the serverless cron tick (ADR-0015)."""

import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, text

from app.agent.orchestrator import Orchestrator
from app.channels.email import EmailChannel, MessageChannel
from app.channels.gmail import GmailChannel
from app.channels.messaging import messaging_channels
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.llm.gateway import Gateway
from app.services import approval, google_calendar, inbox
from app.services.priority import top
from app.tools.registry import build_registry
from app.worker.jobs import Handler, enqueue, run_once

IST = timezone(timedelta(hours=5, minutes=30))


def channels(settings: Settings, engine: Engine) -> dict[str, MessageChannel]:
    email: MessageChannel = (
        GmailChannel(engine, settings)
        if settings.email_provider == "gmail"
        else EmailChannel(
            settings.smtp_host,
            settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
            from_addr=settings.smtp_from,
            redirect_to=settings.email_redirect_to,
            allow_real=settings.email_allow_real,
        )
    )
    return {"email": email, **messaging_channels(settings)}


def send_handlers(settings: Settings) -> dict[str, Handler]:
    return {"send_message": lambda e, p: approval.deliver(e, p["message_id"], channels(settings, e))}


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

    def google_sync(e: Engine, _payload: dict[str, Any]) -> None:
        try:
            if settings.email_provider == "gmail":
                inbox.poll(e, settings)
            google_calendar.sync(e, settings)
        except AppError as err:
            if err.code not in (ErrorCode.GOOGLE_NOT_CONFIGURED, ErrorCode.GOOGLE_NOT_CONNECTED):
                raise  # Google down: the job retries; not set up or disconnected: nothing to do

    return {
        "daily_run": daily_run,
        "promise_check": promise_check,
        "google_sync": google_sync,
        **send_handlers(settings),
    }


def schedule(engine: Engine, now: datetime) -> None:
    """Every 5 minutes while Google is connected: a sync (HACK-009). Once per demo date, from 09:00 IST wall
    time: the daily run and the promise check."""
    with engine.begin() as c:
        if c.execute(text("SELECT 1 FROM google_account WHERE id = 1")).first():
            u = now.astimezone(UTC)
            bucket = u.replace(minute=u.minute - u.minute % 5, second=0, microsecond=0)
            enqueue(c, "google_sync", bucket.isoformat())
            c.execute(
                text(
                    "DELETE FROM jobs WHERE kind = 'google_sync' AND status = 'done' AND created_at < now() - interval '1 day'"
                )
            )
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
