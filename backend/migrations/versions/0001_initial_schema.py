"""Initial schema: every table in docs/design/schema.sql (data model v1).

Revision ID: 0001
Revises:
"""

import re
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SCHEMA = Path(__file__).parents[2] / "app" / "db" / "schema.sql"


def _statements() -> str:
    # The file carries its own BEGIN/COMMIT for psql; Alembic owns the transaction here.
    return re.sub(r"^(BEGIN|COMMIT);$", "", SCHEMA.read_text(encoding="utf-8"), flags=re.M)


def upgrade() -> None:
    op.execute(_statements())


def downgrade() -> None:
    tables = re.findall(r"^CREATE TABLE (\w+) \(", SCHEMA.read_text(encoding="utf-8"), flags=re.M)
    op.execute("DROP VIEW IF EXISTS invoice_balances")
    for table in reversed(tables):
        op.execute(f"DROP TABLE IF EXISTS {table}")
