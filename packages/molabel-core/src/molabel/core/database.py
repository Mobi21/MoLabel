"""Database engine and session helpers (DM-001, DM-002).

One factory builds every SQLite engine MoLabel opens, the server's included,
and sets two pragmas on every connection it hands out: ``journal_mode=WAL``,
so readers never block the writer, and ``foreign_keys=ON``, so a row whose
foreign key points nowhere is refused. SQLite checks a foreign key when a row
is written, not when the pragma is turned on, so rows written before the
pragma can still dangle; :func:`foreign_key_violations` finds them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, event, make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine


def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def engine_from_url(url: str, *, echo: bool = False) -> Engine:
    """Create the engine for *url*, with WAL and foreign keys on every connection.

    An in-memory database gets a :class:`StaticPool`, so every session shares
    the one connection that holds it; ``journal_mode=WAL`` is a no-op there
    and reports ``memory``. An ``sqlite+aiosqlite`` URL is opened with the
    synchronous driver, which is what the app uses throughout.
    """
    url = url.replace("sqlite+aiosqlite", "sqlite")
    parsed = make_url(url)
    kwargs: dict[str, Any] = {"echo": echo}
    if parsed.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if not parsed.database or parsed.database == ":memory:":
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if parsed.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def get_engine(db_path: str | Path, *, echo: bool = False) -> Engine:
    """Create the engine for the SQLite file at *db_path* (see ``engine_from_url``)."""
    return engine_from_url(f"sqlite:///{db_path}", echo=echo)


class ForeignKeyViolation(BaseModel):
    """Rows of one table whose foreign key points at a missing row of another."""

    table: str
    parent: str
    rows: int


def foreign_key_violations(engine: Engine) -> list[ForeignKeyViolation]:
    """Every dangling foreign key in the database, counted per table and parent.

    These rows are reported, never deleted: a review event whose task is gone
    is still a reviewer's decision. Enforcement refuses new ones.
    """
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    counts = Counter((str(row[0]), str(row[2])) for row in rows)
    return [
        ForeignKeyViolation(table=table, parent=parent, rows=count)
        for (table, parent), count in sorted(counts.items())
    ]


@contextmanager
def get_session(engine: Engine) -> Generator[Session, None, None]:
    """Yield a SQLModel session, committing on clean exit.

    Intended for use as a context manager::

        with get_session(engine) as session:
            session.add(obj)
    """
    with Session(engine) as session:
        yield session
