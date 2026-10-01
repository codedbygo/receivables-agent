"""The worker: polls the job table, runs the daily run, promise checks and sends; enqueues the daily run
once per demo date after 09:00 IST (REQ-117). python -m app.worker"""

import logging
import signal
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, text

from app.agent.orchestrator import Orchestrator
from app.channels.email import EmailChannel, MessageChannel, WhatsAppChannel
from app.core.clock import wall_now
from app.core.config import Settings, get_settings
from app.core.db import make_engine
from app.core.logging import configure
from app.llm.gateway import Gateway
from app.services import approval
from app.services.priority import top
from app.tools.registry import build_registry
from app.worker.jobs import Handler, enqueue, reap, run_once

IST = timezone(timedelta(hours=5, minutes=30))
log = logging.getLogger("worker")


def handlers(engine: Engine, settings: Settings) -> dict[str, Handler]:
    orch = Orchestrator(engine, Gateway(settings, engine), build_registry(engine))
    channels: dict[str, MessageChannel] = {
        "email": EmailChannel(settings.smtp_host, settings.smtp_port),
        "whatsapp": WhatsAppChannel(),
    }

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

    def send_message(e: Engine, payload: dict[str, Any]) -> None:
        approval.deliver(e, payload["message_id"], channels)

    return {"daily_run": daily_run, "promise_check": promise_check, "send_message": send_message}


def schedule(engine: Engine, now: datetime) -> None:
    """Once per demo date, from 09:00 IST wall time: the daily run and the promise check."""
    if now.astimezone(IST).hour < 9:
        return
    with engine.begin() as c:
        d = c.execute(text("SELECT demo_today FROM settings WHERE id = 1")).scalar()
        if d is not None:
            enqueue(c, "daily_run", str(d), {"run_date": str(d)})
            enqueue(c, "promise_check", str(d), {"date": str(d)})


def main() -> None:
    configure(get_settings().log_level)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    table = handlers(engine, settings)
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True  # finish the current job, then exit (graceful shutdown)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    last_reap = 0.0
    while not stop:
        try:
            schedule(engine, wall_now())
            if time.monotonic() - last_reap > 60:
                reap(engine)
                last_reap = time.monotonic()
            if run_once(engine, table) is None:
                time.sleep(2)
        except Exception:  # noqa: BLE001  the loop must survive a database restart; the error is logged
            log.exception("worker loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
