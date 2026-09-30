import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"))
        return {r[0] for r in rows} - {"alembic_version"}


def test_upgrade_creates_every_table(engine: Engine) -> None:
    assert len(_tables(engine)) == 21


def test_downgrade_then_upgrade_restores_the_schema(engine: Engine, alembic_cfg: Config) -> None:
    before = _tables(engine)
    command.downgrade(alembic_cfg, "base")
    assert _tables(engine) == set()
    command.upgrade(alembic_cfg, "head")
    assert _tables(engine) == before


def test_money_columns_are_bigint_paise(engine: Engine) -> None:
    sql = text(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND column_name LIKE '%\\_paise'"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).all()
    assert rows, "no money columns found"
    assert {r.data_type for r in rows} == {"bigint"}, rows
