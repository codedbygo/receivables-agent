"""Engine and session factory. Services own transactions (tenet 3)."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


def make_engine(url: str) -> Engine:
    # A serverless function (Vercel sets VERCEL=1) is frozen between requests: hold no pooled connections.
    pool = {"poolclass": NullPool} if os.environ.get("VERCEL") == "1" else {}
    return create_engine(
        url, pool_pre_ping=True, hide_parameters=True, connect_args={"connect_timeout": 3}, **pool
    )


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any error."""
    with factory() as session, session.begin():
        yield session


def ping(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001  readiness reports any failure as unavailable
        return False
