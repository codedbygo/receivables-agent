"""HACK-003: follow up tasks (app/db/upgrade_0003.sql, app/db/downgrade_0003.sql).

Revision ID: 0003
Revises: 0002
"""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"

DB = Path(__file__).parents[2] / "app" / "db"


def upgrade() -> None:
    op.execute((DB / "upgrade_0003.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute((DB / "downgrade_0003.sql").read_text(encoding="utf-8"))
