"""Alembic environment: plain SQL migrations, URL from DATABASE_URL."""

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
