"""Automatic database migration runner (DB-003, DB-004, DB-006).

Detects the current schema version, optionally backs up the database,
and applies any pending Alembic migrations.  Intended to be called on
FastAPI startup so users never see an out-of-date schema.
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, event, pool

logger = logging.getLogger(__name__)

# The migrations directory lives alongside this module inside molabel-core.
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _set_sqlite_wal(engine) -> None:
    """Attach WAL and FK pragma listeners to a SQLAlchemy engine."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _make_alembic_config(db_url: str) -> AlembicConfig:
    """Build a programmatic Alembic Config (no alembic.ini needed)."""
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _db_url_from_path(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


# ------------------------------------------------------------------
# DB-006: Schema version query
# ------------------------------------------------------------------


def get_schema_version(db_path: Path) -> str | None:
    """Read the current Alembic schema version from a database.

    Returns ``None`` if no ``alembic_version`` table exists (i.e. the
    database has never been migrated).
    """
    url = _db_url_from_path(db_path)
    engine = engine_from_config(
        {"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    _set_sqlite_wal(engine)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            heads = ctx.get_current_heads()
            return heads[0] if heads else None
    finally:
        engine.dispose()


# ------------------------------------------------------------------
# DB-004: Pre-migration backup
# ------------------------------------------------------------------


def _backup_database(db_path: Path) -> Path:
    """Copy the SQLite file to a timestamped backup and return the path."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_suffix(f".backup.{ts}.sqlite")
    shutil.copy2(db_path, backup_path)
    logger.info("Database backed up to %s", backup_path)
    return backup_path


def _has_pending_migrations(db_path: Path) -> bool:
    """Return True when there are Alembic revisions newer than the DB."""
    url = _db_url_from_path(db_path)
    cfg = _make_alembic_config(url)
    script = ScriptDirectory.from_config(cfg)

    engine = engine_from_config(
        {"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    _set_sqlite_wal(engine)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current_heads = set(ctx.get_current_heads())
            script_heads = set(script.get_heads())
            return current_heads != script_heads
    finally:
        engine.dispose()


# ------------------------------------------------------------------
# DB-003 / DB-005: Run pending migrations (supports multi-skip)
# ------------------------------------------------------------------


def run_migrations(db_path: Path) -> None:
    """Detect current schema version and apply all pending migrations.

    1. Check for pending migrations.
    2. If any exist, back up the database file (DB-004).
    3. Run ``alembic upgrade head`` programmatically (DB-005 — Alembic
       handles multi-skip natively via its revision chain).
    4. Log progress for every step.

    Parameters
    ----------
    db_path:
        Absolute path to the workspace SQLite database file.
    """
    if not db_path.exists():
        logger.info(
            "Database %s does not exist yet; migrations will create it.", db_path
        )

    url = _db_url_from_path(db_path)

    # Check whether anything needs to be done.
    if db_path.exists() and not _has_pending_migrations(db_path):
        logger.info("Database schema is up-to-date — no migrations to run.")
        return

    # DB-004: back up before touching an existing database.
    if db_path.exists():
        _backup_database(db_path)

    logger.info("Running database migrations for %s …", db_path)

    cfg = _make_alembic_config(url)

    # Provide the connection to env.py via config.attributes so that we
    # share a single engine with WAL pragma.
    engine = engine_from_config(
        {"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    _set_sqlite_wal(engine)
    try:
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            alembic_command.upgrade(cfg, "head")
    finally:
        engine.dispose()

    new_version = get_schema_version(db_path)
    logger.info("Migrations complete — schema is now at revision %s.", new_version)
