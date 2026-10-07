"""HACK-007: timeline kinds for distributor and invoice management (app/db/upgrade_0008.sql, app/db/downgrade_0008.sql).

Revision ID: 0008
Revises: 0007
"""

from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"

DB = Path(__file__).parents[2] / "app" / "db"


def upgrade() -> None:
    op.execute((DB / "upgrade_0008.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute((DB / "downgrade_0008.sql").read_text(encoding="utf-8"))
