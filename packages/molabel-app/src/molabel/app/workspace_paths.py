"""Confine request-supplied paths to registered workspace roots.

Every path a request names, directly or through stored config, reaches the
filesystem only through this module. A path must not contain ``..``, and
after ``resolve()`` (symlinks included) it must be a registered workspace
root or inside one. The one exception is bootstrap, which registers a new
root and so only requires an absolute path without ``..``.
"""

from __future__ import annotations

from dataclasses import dataclass
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
