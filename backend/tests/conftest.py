"""Shared fixtures. Tests marked integration need Postgres at DATABASE_URL
(make up locally, a service container in CI); everything else runs offline."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

BACKEND = Path(__file__).parents[1]

# Tests sign in with the role header, which is only honoured on a laptop (see app/services/auth.py).
os.environ.setdefault("DEMO_OPEN_ROLES", "true")


def _alembic() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail("integration tests need DATABASE_URL (run make up); they never skip silently")
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(_alembic(), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    trans.rollback()
    conn.close()


@pytest.fixture
def alembic_cfg() -> Config:
    return _alembic()
