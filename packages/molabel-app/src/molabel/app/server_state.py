"""Where the server keeps its own state: one database and one app secret.

The server serves every registered workspace from a single SQLite database.
It lives in a per-user data directory, never in the folder the server was
launched from and never inside a workspace.

Earlier versions kept the database at ``./molabel.db`` in the launch folder,
and bootstrap wrote one at ``<workspace>/workbench/molabel.db``. Neither is
merged in. While the server database holds no workspace, a populated one is
reported as a legacy database, with the setting that makes the server use it.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, text


def server_data_dir() -> Path:
    """Return the server's data directory, honouring ``MOLABEL_DATA_DIR``."""
    override = os.environ.get("MOLABEL_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "MoLabel"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MoLabel"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "molabel"


def server_db_url() -> str:
    """Return ``MOLABEL_DB_URL``, or the SQLite file in the data directory."""
    override = os.environ.get("MOLABEL_DB_URL")
    if override:
        return override
    data_dir = server_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'molabel.db').as_posix()}"


class LegacyDatabase(BaseModel):
    """A populated database from an earlier version that the server does not read."""

    path: str
    workspace_count: int
    adopt: str
    message: str


def launch_folder_database() -> Path:
    """Where earlier versions kept the server database by default."""
    return Path.cwd() / "molabel.db"


def _workspace_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as conn:
            return int(conn.execute("SELECT count(*) FROM workspaces").fetchone()[0])
    except sqlite3.Error:
        return 0


def legacy_databases(
    engine: Engine, candidates: Iterable[Path]
) -> list[LegacyDatabase]:
    """The populated *candidates*, while the server database holds no workspace."""
    with engine.connect() as conn:
        if conn.execute(text("SELECT count(*) FROM workspaces")).scalar_one():
            return []
    server = engine.url.render_as_string(hide_password=True)
    server_file = (
        Path(engine.url.database).resolve()
        if engine.url.get_backend_name() == "sqlite" and engine.url.database
        else None
    )
    found: list[LegacyDatabase] = []
    for candidate in candidates:
        path = candidate.resolve()
        count = _workspace_count(path) if path != server_file else 0
        if count == 0:
            continue
        adopt = f"MOLABEL_DB_URL=sqlite:///{path.as_posix()}"
        found.append(
            LegacyDatabase(
                path=str(path),
                workspace_count=count,
                adopt=adopt,
                message=(
                    f"{path} is a MoLabel database from an earlier version and "
                    f"lists {count} workspace(s). This server uses {server} and "
                    "does not read it, so they are not shown. To use it instead, "
                    f"restart the server with {adopt}. The server backs it up "
                    "and upgrades it on start."
                ),
            )
        )
    return found
