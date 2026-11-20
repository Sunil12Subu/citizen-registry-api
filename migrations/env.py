"""Alembic migration environment.

Alembic runs this file for every migration command. We point it at:
- our database URL (read from .env via config.py, never hardcoded), and
- our models' metadata, so `--autogenerate` can compare models vs. the real database.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from citizen_registry_api.config import get_settings
from citizen_registry_api.models import Base

config = context.config

# Inject the real DB URL at runtime. "%" is escaped because .ini files treat it as special.
db_url = get_settings().database_url.get_secret_value()
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The tables Alembic should know about
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL scripts without connecting (e.g. for a DBA to review)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # also detect column type changes, e.g. String(100) -> String(200)
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
