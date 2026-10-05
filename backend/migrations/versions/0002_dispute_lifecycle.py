"""HACK-003: dispute lifecycle (app/db/upgrade_0002.sql, app/db/downgrade_0002.sql).

Revision ID: 0002
Revises: 0001
"""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"

DB = Path(__file__).parents[2] / "app" / "db"


def upgrade() -> None:
    op.execute((DB / "upgrade_0002.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute((DB / "downgrade_0002.sql").read_text(encoding="utf-8"))
