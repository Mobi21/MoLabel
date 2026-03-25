"""Database engine, table creation, and session helpers (DM-001, DM-002).

Provides a thin wrapper around SQLModel / SQLAlchemy for the MoLabel
operational SQLite database.  The engine is configured with WAL mode for
concurrent reader support.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine


def get_engine(db_path: str | Path, *, echo: bool = False):
    """Create a SQLite engine with WAL journal mode.

    Parameters
    ----------
    db_path:
        File-system path for the SQLite database.  Use ``:memory:`` for
        an in-memory database (WAL pragma is silently skipped).
    echo:
        If *True*, emit SQL statements to the default logger.
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=echo)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_all_tables(engine) -> None:
    """Create every table registered with SQLModel metadata.

    All model modules must be imported before calling this function so
    that their tables are registered.  The ``molabel.core.models``
    package import achieves this.
    """
    # Ensure all model classes are loaded into SQLModel.metadata.
    import molabel.core.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session(engine) -> Generator[Session, None, None]:
    """Yield a SQLModel session, committing on clean exit.

    Intended for use as a context manager::

        with get_session(engine) as session:
            session.add(obj)
    """
    with Session(engine) as session:
        yield session
