from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from learning.core.config import settings
from learning.db.base import Base

# Importing the models package registers every mapper on Base.metadata,
# which is what autogenerate diffs against.
import learning.models  # noqa: F401

config = context.config

# The URL comes from .env via Settings, never alembic.ini. It is NOT written back
# into the ini: configparser treats "%" as interpolation syntax and would choke on
# a percent-encoded password.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run migrations against it."""
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
