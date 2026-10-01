"""Postgres job queue (ADR-0006): SKIP LOCKED claim, unique (kind, dedupe_key), backoff, dead letters."""

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection


class Defer(Exception):
    """Try again later without spending an attempt (kill switch on)."""


Handler = Callable[[Engine, dict[str, Any]], None]


def enqueue(conn: Connection, kind: str, key: str, payload: dict[str, Any] | None = None) -> int | None:
    """Idempotent: a second enqueue of the same (kind, key) returns None and changes nothing."""
    job_id = conn.execute(
        text("""INSERT INTO jobs (kind, dedupe_key, payload) VALUES (:k, :d, CAST(:p AS jsonb))
        ON CONFLICT (kind, dedupe_key) DO NOTHING RETURNING id"""),
        {"k": kind, "d": key, "p": json.dumps(payload or {})},
    ).scalar()
    return int(job_id) if job_id is not None else None


def run_once(engine: Engine, handlers: dict[str, Handler]) -> str | None:
    """Claim one due job, run it, record the result. Returns the job kind, or None when idle."""
    with engine.begin() as c:
        job = c.execute(
            text("""SELECT id, kind, payload, attempts, max_attempts FROM jobs
            WHERE status = 'queued' AND run_at <= now() ORDER BY run_at, id FOR UPDATE SKIP LOCKED LIMIT 1""")
        ).first()
        if job is None:
            return None
        c.execute(
            text(
                "UPDATE jobs SET status = 'running', locked_at = now(), attempts = attempts + 1 WHERE id = :i"
            ),
            {"i": job.id},
        )
    try:
        handlers[job.kind](engine, dict(job.payload))
    except Defer:
        with engine.begin() as c:
            c.execute(
                text("""UPDATE jobs SET status = 'queued', attempts = attempts - 1, locked_at = NULL,
                run_at = now() + interval '15 seconds' WHERE id = :i"""),
                {"i": job.id},
            )
        return str(job.kind)
    except Exception as e:  # noqa: BLE001  any handler failure is recorded on the job, never swallowed
        dead = job.attempts + 1 >= job.max_attempts
        delay = timedelta(seconds=10 * 2**job.attempts)
        with engine.begin() as c:
            c.execute(
                text("""UPDATE jobs SET status = :s, locked_at = NULL, last_error = :e,
                run_at = now() + :d WHERE id = :i"""),
                {
                    "s": "dead" if dead else "queued",
                    "e": f"{type(e).__name__}: {e}"[:300],
                    "d": delay,
                    "i": job.id,
                },
            )
        return str(job.kind)
    with engine.begin() as c:
        c.execute(
            text("UPDATE jobs SET status = 'done', locked_at = NULL, last_error = NULL WHERE id = :i"),
            {"i": job.id},
        )
    return str(job.kind)


def reap(engine: Engine) -> int:
    """Requeue jobs locked over 5 minutes. A send whose message is IN_FLIGHT is never retried:
    the mail may have left, so the message becomes failed/UNCONFIRMED (HLD section 7)."""
    with engine.begin() as c:
        stale = c.execute(
            text("""SELECT id, kind, payload FROM jobs WHERE status = 'running'
            AND locked_at < now() - interval '5 minutes' FOR UPDATE SKIP LOCKED""")
        ).all()
        for j in stale:
            if j.kind == "send_message":
                c.execute(
                    text("""UPDATE messages SET status = 'failed', last_error = 'UNCONFIRMED', updated_at = now()
                    WHERE id = CAST(:m AS uuid) AND last_error = 'IN_FLIGHT'"""),
                    {"m": j.payload["message_id"]},
                )
                c.execute(
                    text("UPDATE jobs SET status = 'dead', last_error = 'UNCONFIRMED' WHERE id = :i"),
                    {"i": j.id},
                )
            else:
                c.execute(
                    text("UPDATE jobs SET status = 'queued', locked_at = NULL WHERE id = :i"), {"i": j.id}
                )
    return len(stale)
