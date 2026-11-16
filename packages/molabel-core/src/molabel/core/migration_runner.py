"""Bring a MoLabel database to the latest Alembic revision (DB-003, DB-004).

Alembic is the only thing that creates or alters tables. A database created
by ``SQLModel.metadata.create_all`` before Alembic owned the schema has tables
but no ``alembic_version``; it is stamped at the baseline revision, whose DDL
is frozen at exactly that schema, and then upgraded like any other.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

#: The revision whose DDL equals the pre-Alembic ``create_all`` schema.
BASELINE_REVISION = "001"


def _alembic_config(engine: Engine) -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False)
    )
    return cfg


def _sqlite_file(engine: Engine) -> Path | None:
    database = engine.url.database
    if engine.url.get_backend_name() != "sqlite" or not database:
        return None
    if database == ":memory:" or database.startswith("file:"):
        return None
    path = Path(database)
    return path if path.is_file() and path.stat().st_size > 0 else None


def _backup(db_path: Path) -> Path:
    """Copy the database through SQLite, so rows still in the WAL are included."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_suffix(f".backup.{ts}.sqlite")
    with (
        closing(sqlite3.connect(db_path)) as source,
        closing(sqlite3.connect(backup_path)) as target,
    ):
        source.backup(target)
    logger.info("Database backed up to %s", backup_path)
    return backup_path


def upgrade_database(engine: Engine) -> None:
    """Run ``alembic upgrade head`` on *engine*, stamping pre-Alembic databases."""
    cfg = _alembic_config(engine)
    head = ScriptDirectory.from_config(cfg).get_current_head()

    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_heads()
    if current == (head,):
        return

    db_file = _sqlite_file(engine)
    if db_file is not None:
        _backup(db_file)

    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if tables and "alembic_version" not in tables:
            logger.info(
                "Stamping pre-Alembic database at baseline %s", BASELINE_REVISION
            )
            alembic_command.stamp(cfg, BASELINE_REVISION)
        alembic_command.upgrade(cfg, "head")
    logger.info("Database schema is at revision %s", head)
