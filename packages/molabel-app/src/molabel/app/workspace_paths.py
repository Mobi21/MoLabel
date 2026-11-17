"""Confine request-supplied paths to registered workspace roots.

Every path a request names, directly or through stored config, and every
path the server derives under a workspace root, reaches the filesystem only
through this module. A path must not contain ``..``, and
after ``resolve()`` (symlinks included) it must be a registered workspace
root or inside one. The one exception is bootstrap, which registers a new
root and so only requires an absolute path without ``..``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from molabel.app.schemas import ErrorDetail, ErrorResponse


class WorkspacePathError(Exception):
    """A request path that the server refuses to touch."""

    def __init__(self, status_code: int, code: str, message: str, path: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.path = path


async def workspace_path_error_handler(
    _request: Request, exc: WorkspacePathError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code, message=exc.message, details={"path": exc.path}
            )
        ).model_dump(mode="json"),
    )


@dataclass(frozen=True)
class WorkspaceRoot:
    workspace_id: str
    path: Path


def _reject_traversal(raw: str) -> None:
    if ".." in PurePosixPath(raw.replace("\\", "/")).parts:
        raise WorkspacePathError(
            400, "PATH_TRAVERSAL", "Paths must not contain '..' segments", raw
        )


_WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {
        f"{port}{number}"
        for port in ("com", "lpt")
        for number in [*"0123456789", chr(0xB9), chr(0xB2), chr(0xB3)]
    }
)


def portable_name_problem(name: str) -> str | None:
    """Why Windows cannot hold a file or folder called *name*, or None.

    Windows drops a trailing dot or space, and reserves its device names in
    any case and with any extension.
    """
    if name != name.rstrip(" ."):
        return f"'{name}' ends with a dot or a space, which Windows drops"
    if name.split(".", 1)[0].rstrip(" ").lower() in _WINDOWS_DEVICES:
        return f"'{name}' is a device name Windows reserves"
    return None


def require_portable(root: Path, raw: str) -> None:
    """Refuse to write *raw* when a folder or file name in it is not portable.

    A workspace is committed to git and opened on other machines, so every
    name MoLabel writes must work on Windows, whatever platform writes it.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        if not path.is_relative_to(root):
            return
        path = path.relative_to(root)
    for name in path.parts:
        if name in (".", ".."):
            continue
        problem = portable_name_problem(name)
        if problem is not None:
            raise WorkspacePathError(
                422,
                "PATH_NOT_PORTABLE",
                f"{problem}, so the workspace would not open there. Pick another name.",
                raw,
            )


def new_workspace_root(raw: str) -> Path:
    """Validate a path the caller is about to register as a workspace root."""
    _reject_traversal(raw)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise WorkspacePathError(
            400, "PATH_NOT_ABSOLUTE", "Workspace paths must be absolute", raw
        )
    return path.resolve()


def resolve_in_workspace(root: Path, raw: str) -> Path:
    """Resolve *raw* against *root*, refusing anything that ends up outside it."""
    _reject_traversal(raw)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise WorkspacePathError(
            403,
            "PATH_OUTSIDE_WORKSPACE",
            "Path is outside the workspace",
            raw,
        )
    return resolved


@dataclass(frozen=True)
class WorkspaceMatch:
    """A glob match at *path* under its base, and the *resolved* file it reached.

    Show and relativize *path*, which may pass through a link inside the
    workspace. Open *resolved*, the target the containment check approved,
    so a link swapped after the check cannot redirect the read.
    """

    path: Path
    resolved: Path


def glob_in_workspace(root: Path, base: Path, pattern: str) -> list[WorkspaceMatch]:
    """Entries under *base* whose name matches ``**/<name>`` *pattern*.

    Linked folders are followed on every platform (``Path.glob`` follows
    Windows junctions but not POSIX symlinks), each folder is visited once so
    a link cycle ends, and any match resolving outside *root* is refused.
    """
    prefix = "**/"
    if not pattern.startswith(prefix) or "/" in pattern[len(prefix) :]:
        raise ValueError(f"Unsupported workspace glob pattern: {pattern!r}")
    name_pattern = pattern[len(prefix) :]
    if not base.is_dir():
        return []
    hits: list[Path] = []
    visited: set[Path] = set()
    for dirpath, dirnames, filenames in base.walk(follow_symlinks=True):
        real = dirpath.resolve()
        if real in visited:
            dirnames.clear()
            continue
        visited.add(real)
        hits.extend(
            dirpath / name
            for name in (*dirnames, *filenames)
            if fnmatch(name, name_pattern)
        )
    return [
        WorkspaceMatch(hit, resolve_in_workspace(root, str(hit)))
        for hit in sorted(hits)
    ]


def registered_root(conn, workspace_id: str) -> Path | None:
    """The resolved root of workspace *workspace_id*, or None if it has none."""
    row = conn.execute(
        text("SELECT root_path FROM workspaces WHERE id = :id"),
        {"id": workspace_id},
    ).first()
    if row is None or not row[0]:
        return None
    return Path(str(row[0])).expanduser().resolve()


def request_workspace(
    engine, *, workspace_root: str | None, workspace_id: str | None
) -> WorkspaceRoot:
    """The registered workspace a request names by root path, by id, or both."""
    if workspace_root is None and workspace_id is None:
        raise WorkspacePathError(
            400,
            "WORKSPACE_REQUIRED",
            "Pass workspace_root or workspace_id",
            "",
        )
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, root_path FROM workspaces")).fetchall()
    roots = [
        WorkspaceRoot(str(row[0]), Path(str(row[1])).expanduser().resolve())
        for row in rows
        if row[1]
    ]
    if workspace_id is not None:
        roots = [root for root in roots if root.workspace_id == workspace_id]
        if not roots:
            raise WorkspacePathError(
                404, "NOT_FOUND", "Workspace not found", workspace_id
            )
    if workspace_root is None:
        return roots[0]

    _reject_traversal(workspace_root)
    candidate = Path(workspace_root).expanduser()
    if not candidate.is_absolute():
        raise WorkspacePathError(
            400, "PATH_NOT_ABSOLUTE", "workspace_root must be absolute", workspace_root
        )
    resolved = candidate.resolve()
    containing = [root for root in roots if resolved.is_relative_to(root.path)]
    if not containing:
        raise WorkspacePathError(
            403,
            "PATH_OUTSIDE_WORKSPACE",
            "workspace_root is not inside a registered workspace",
            workspace_root,
        )
    return max(containing, key=lambda root: len(root.path.parts))
