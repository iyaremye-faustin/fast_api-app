"""Console entry points. Wired up in pyproject.toml under [project.scripts]."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

# src/learning/cli.py -> src/learning -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Canonical env.py. Kept here so re-scaffolding never loses our customisations
# (alembic init writes a default env.py that reads the URL from alembic.ini).
ENV_PY = '''from logging.config import fileConfig

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
'''


def _script_dir(cfg: Config) -> Path:
    return Path(cfg.get_main_option("script_location"))


def _ensure_scaffolding(cfg: Config) -> None:
    """Recreate env.py / script.py.mako / versions/ if they are missing.

    Losing the alembic directory should be recoverable without re-running
    `alembic init` by hand.
    """
    target = _script_dir(cfg)
    if (target / "env.py").exists() and (target / "versions").is_dir():
        return

    print(f"Migration scaffolding missing at {target} — creating it.")
    if target.exists():
        # init refuses a non-empty directory; fill in only what is absent.
        (target / "versions").mkdir(parents=True, exist_ok=True)
        if not (target / "script.py.mako").exists():
            import alembic

            mako = Path(alembic.__file__).parent / "templates" / "generic" / "script.py.mako"
            (target / "script.py.mako").write_text(mako.read_text())
    else:
        command.init(cfg, str(target), template="generic")

    # Always (re)write env.py: init's default version cannot read our settings.
    (target / "env.py").write_text(ENV_PY)


def _clear_orphaned_version(cfg: Config) -> None:
    """Drop an alembic_version pointer left behind by deleted migration files.

    Only acts when there are NO migration files at all — i.e. the history was
    deliberately wiped. With files present, a mismatch is a real problem the
    user needs to see rather than something to paper over.
    """
    from learning.core.config import settings

    if any(ScriptDirectory.from_config(cfg).walk_revisions()):
        return  # history exists; never touch the version table

    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        if "alembic_version" not in inspect(conn).get_table_names():
            return
        stale = [r[0] for r in conn.execute(text("select version_num from alembic_version"))]
        if not stale:
            return
        print(f"No migration files exist, but the database still points at {stale}. Clearing it.")
        conn.execute(text("delete from alembic_version"))
        conn.commit()


def _needs_baseline(cfg: Config) -> bool:
    """True when there are no migrations but the schema already exists.

    Happens after deleting versions/: the tables are still there, so a plain
    autogenerate would produce an empty migration instead of the full schema.
    """
    from learning.core.config import settings
    from learning.db.base import Base

    import learning.models  # noqa: F401

    if any(ScriptDirectory.from_config(cfg).walk_revisions()):
        return False

    with create_engine(settings.DATABASE_URL).connect() as conn:
        existing = set(inspect(conn).get_table_names())
    return bool(existing & set(Base.metadata.tables))


def _baseline(cfg: Config, message: str) -> None:
    """Generate a full-schema migration and stamp it without re-running the DDL.

    Autogenerate diffs against a scratch EMPTY database so the migration contains
    real CREATE TABLEs. Using an empty database on the same server keeps the
    rendered types correct for this dialect.
    """
    from sqlalchemy.engine import make_url

    from learning.core.config import settings

    real_url = make_url(settings.DATABASE_URL)
    print("No migrations exist but the schema is already present — writing a baseline migration.")

    if real_url.drivername.startswith("sqlite"):
        scratch = real_url.set(database=str(PROJECT_ROOT / ".alembic-baseline.tmp")).render_as_string(hide_password=False)
        cleanup = lambda: Path(PROJECT_ROOT / ".alembic-baseline.tmp").unlink(missing_ok=True)  # noqa: E731
    else:
        tmp_name = f"{real_url.database}_alembic_tmp"
        server = create_engine(real_url.set(database=None).render_as_string(hide_password=False))
        with server.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS `{tmp_name}`"))
            c.execute(text(f"CREATE DATABASE `{tmp_name}`"))
            c.commit()
        scratch = real_url.set(database=tmp_name).render_as_string(hide_password=False)

        def cleanup() -> None:
            with server.connect() as c:
                c.execute(text(f"DROP DATABASE IF EXISTS `{tmp_name}`"))
                c.commit()

    original = settings.DATABASE_URL
    try:
        settings.DATABASE_URL = scratch  # env.py reads this at run time
        command.revision(cfg, message=message, autogenerate=True)
    finally:
        settings.DATABASE_URL = original
        cleanup()

    command.stamp(cfg, "head", purge=True)
    print("Baseline recorded: the migration describes the existing schema and is marked applied.")


def _alembic_config(*, repair: bool = False) -> Config:
    ini = PROJECT_ROOT / "alembic.ini"
    if not ini.exists():
        sys.exit(f"alembic.ini not found at {ini}")
    cfg = Config(str(ini))
    if repair:
        _ensure_scaffolding(cfg)
        _clear_orphaned_version(cfg)
    return cfg


def makemigrations() -> None:
    """Autogenerate a migration from model changes.

    usage: uv run makemigrations "add phone to users"
    """
    message = " ".join(sys.argv[1:]).strip()
    if not message:
        sys.exit('A message is required, e.g. uv run makemigrations "add phone to users"')

    cfg = _alembic_config(repair=True)

    if _needs_baseline(cfg):
        _baseline(cfg, message)
        return

    command.revision(cfg, message=message, autogenerate=True)
    print("\nReview the generated file before applying it — Alembic cannot detect renames.")


def migrate() -> None:
    """Apply migrations.

    usage: uv run migrate            # up to the latest revision
           uv run migrate <revision> # up to a specific revision
    """
    target = sys.argv[1] if len(sys.argv) > 1 else "head"
    command.upgrade(_alembic_config(repair=True), target)


def rollback() -> None:
    """Revert migrations.

    usage: uv run rollback      # undo the last migration
           uv run rollback 2    # undo the last 2
           uv run rollback base # undo everything
    """
    arg = sys.argv[1] if len(sys.argv) > 1 else "1"

    if arg.isdigit():
        target = f"-{arg}"
    else:
        target = arg  # "base", "-N", or an explicit revision id

    if target == "base":
        print("This reverts EVERY migration and drops all tables it created.")
        if input("Type 'yes' to continue: ").strip().lower() != "yes":
            sys.exit("Aborted.")

    command.downgrade(_alembic_config(), target)


def migration_status() -> None:
    """Show the current revision and the migration history."""
    cfg = _alembic_config(repair=True)
    print("--- current ---")
    command.current(cfg, verbose=True)
    print("--- history ---")
    command.history(cfg, indicate_current=True)


def dev() -> None:
    """Run the development server with autoreload."""
    import uvicorn

    uvicorn.run("learning.main:app", reload=True)
