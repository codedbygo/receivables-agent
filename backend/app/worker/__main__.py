"""The worker: polls the job table, runs the daily run, promise checks and sends; enqueues the daily run
once per demo date after 09:00 IST (REQ-117). python -m app.worker"""

import logging
import signal
import time

from app.core.clock import wall_now
from app.core.config import get_settings
from app.core.db import make_engine
from app.core.logging import configure
from app.worker.jobs import reap, run_once
from app.worker.runner import handlers, schedule

log = logging.getLogger("worker")


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
