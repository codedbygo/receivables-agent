"""HACK-011: people sign in with a password or Google (app/db/upgrade_0010.sql, downgrade_0010.sql).

Revision ID: 0010
Revises: 0009
"""

from pathlib import Path

from alembic import op

revision = "0010"
down_revision = "0009"

DB = Path(__file__).parents[2] / "app" / "db"


def upgrade() -> None:
    op.execute((DB / "upgrade_0010.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute((DB / "downgrade_0010.sql").read_text(encoding="utf-8"))
