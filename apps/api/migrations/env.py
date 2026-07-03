"""Alembic environment: resolves the URL from validated app settings."""

from alembic import context
from sqlalchemy import create_engine, pool

from citebear_api.config import get_settings
from citebear_api.db import async_database_url
from citebear_api.models import Base

target_metadata = Base.metadata


def _database_url() -> str:
    return async_database_url(get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
