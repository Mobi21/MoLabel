"""Where the server keeps its own state: one database and one app secret.

The server serves every registered workspace from a single SQLite database.
It lives in a per-user data directory, never in the folder the server was
launched from and never inside a workspace.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


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
