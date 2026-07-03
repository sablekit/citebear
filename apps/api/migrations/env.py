"""Alembic environment: resolves DATABASE_URL itself so migrations run
in environments that lack the app's other required settings."""

from alembic import context
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, pool

from citebear_api.db import async_database_url
from citebear_api.models import Base

target_metadata = Base.metadata


class _MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str


def _database_url() -> str:
    return async_database_url(_MigrationSettings().database_url)  # pyright: ignore[reportCallIssue]


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
