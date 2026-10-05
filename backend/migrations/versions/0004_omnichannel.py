"""HACK-003: omnichannel (app/db/upgrade_0004.sql, app/db/downgrade_0004.sql).

Revision ID: 0004
Revises: 0003
"""

from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"

DB = Path(__file__).parents[2] / "app" / "db"


def upgrade() -> None:
    op.execute((DB / "upgrade_0004.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute((DB / "downgrade_0004.sql").read_text(encoding="utf-8"))
