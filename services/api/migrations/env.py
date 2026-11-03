"""Alembic environment: migrations run as the application login against the repository database."""

from alembic import context
from sqlalchemy import create_engine

from eax.config import get_settings

config = context.config
if config.config_file_name is not None:
    from logging.config import fileConfig

    fileConfig(config.config_file_name)


def run_migrations_online() -> None:
    engine = create_engine(get_settings().sqlalchemy_url)
    with engine.connect() as connection:
        context.configure(connection=connection, version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(url=get_settings().sqlalchemy_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
