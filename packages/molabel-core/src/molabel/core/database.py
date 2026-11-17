"""Database engine and session helpers (DM-001, DM-002).

One factory builds every SQLite engine MoLabel opens, the server's included,
and sets two pragmas on every connection it hands out: ``journal_mode=WAL``,
so readers never block the writer, and ``foreign_keys=ON``, so a row whose
foreign key points nowhere is refused. SQLite checks a foreign key when a row
is written, not when the pragma is turned on, so rows written before the
pragma can still dangle; :func:`foreign_key_violations` finds them.

:class:`HyphenatedUuid` is the column type of every UUID in the models. It
stores the 36-character hyphenated form, the one every route writes through
raw SQL, so rows from the two paths reference each other.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Dialect, Engine, Uuid, event, make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine


class HyphenatedUuid(Uuid[uuid.UUID]):
    """A UUID column that stores the hyphenated form, ``str(uuid)``.

    ``sa.Uuid`` stores ``uuid.hex`` on SQLite, while every route writes
    ``str(uuid)`` through raw SQL, so a row from one path never matched a
    row from the other, neither in a foreign key nor in ``session.get``
    (#29). This type binds the hyphenated form and accepts a string spelling
    too. Reading is inherited: ``uuid.UUID`` parses either form. The DDL is
    inherited as well, ``CHAR(32)`` on SQLite, which every existing database
    declares; SQLite does not enforce the length.
    """

    def bind_processor(
        self, dialect: Dialect
    ) -> Callable[[uuid.UUID | str | None], Any] | None:
        if dialect.supports_native_uuid and self.native_uuid:
            return super().bind_processor(dialect)

        def process(value: uuid.UUID | str | None) -> str | None:
            if value is None:
                return None
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(str(value))
            return str(value)

        return process

    def literal_processor(
        self, dialect: Dialect
    ) -> Callable[[uuid.UUID | str], str] | None:
        if dialect.supports_native_uuid and self.native_uuid:
            return super().literal_processor(dialect)
        bind = self.bind_processor(dialect)
        assert bind is not None

        def process(value: uuid.UUID | str) -> str:
            return f"'{bind(value)}'"

        return process


def hyphenated_id(value: str) -> str:
    """``value`` as a UUID column stores it, or ``value`` if it is not a UUID.

    An id read from JSON can be in any spelling ``uuid.UUID`` reads, such as
    the 32-hex form written before revision 005, and a lookup on a UUID
    column matches only the hyphenated form.
    """
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return value


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
    """Every row with a dangling foreign key, counted per table and parent.

    These rows are reported, never deleted: a review event whose task is gone
    is still a reviewer's decision. Enforcement refuses new ones. SQLite
    reports one line per violated constraint, so a row with two keys to the
    same parent is counted once.
    """
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    dangling = {(str(row[0]), row[1], str(row[2])) for row in rows}
    counts = Counter((table, parent) for table, _rowid, parent in dangling)
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
