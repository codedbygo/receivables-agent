"""HACK-009: Google account, Gmail threads, incoming replies, calendar events (app/db/upgrade_0009.sql, downgrade_0009.sql).

Revision ID: 0009
Revises: 0008
"""

from pathlib import Path

from alembic import op

revision = "0009"
down_revision = "0008"

DB = Path(__file__).parents[2] / "app" / "db"


def upgrade() -> None:
    op.execute((DB / "upgrade_0009.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute((DB / "downgrade_0009.sql").read_text(encoding="utf-8"))
