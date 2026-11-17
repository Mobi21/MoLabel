"""Confine request-supplied paths to registered workspace roots.

Every path a request names, directly or through stored config, and every
path the server derives under a workspace root, reaches the filesystem only
through this module. A path must not contain ``..``, and
after ``resolve()`` (symlinks included) it must be a registered workspace
root or inside one.

Registering a root is the one way to widen that boundary, so a new root must
resolve, links and junctions followed, to a folder strictly inside an allowed
parent: ``MOLABEL_ALLOWED_WORKSPACE_ROOTS``, or the home folder by default.
Drive and share roots, the home folder, and each allowed parent itself are
refused.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatch
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from molabel.app.schemas import ErrorDetail, ErrorResponse

ALLOWED_ROOTS_ENV = "MOLABEL_ALLOWED_WORKSPACE_ROOTS"


class WorkspacePathError(Exception):
    """A request path that the server refuses to touch."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        path: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.path = path
        self.details = details or {}


async def workspace_path_error_handler(
    _request: Request, exc: WorkspacePathError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                details={"path": exc.path, **exc.details},
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
        for number in [*"123456789", chr(0xB9), chr(0xB2), chr(0xB3)]
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


class RootRefusal(StrEnum):
    """Why a folder may not be registered as a workspace root."""

    FILESYSTEM_ROOT = "filesystem_root"
    HOME_FOLDER = "home_folder"
    ALLOWED_PARENT = "allowed_parent"
    OUTSIDE_ALLOWED_PARENTS = "outside_allowed_parents"


_REFUSAL_TEXT = {
    RootRefusal.FILESYSTEM_ROOT: "is a drive or share root",
    RootRefusal.HOME_FOLDER: "is the home folder",
    RootRefusal.ALLOWED_PARENT: "is an allowed parent folder itself",
    RootRefusal.OUTSIDE_ALLOWED_PARENTS: "is outside the allowed parent folders",
}


@dataclass(frozen=True)
class RootPolicy:
    """The folders a workspace root may be registered under, all resolved."""

    home: PurePath
    allowed_parents: Sequence[PurePath]

    @classmethod
    def from_env(cls) -> RootPolicy:
        """``MOLABEL_ALLOWED_WORKSPACE_ROOTS`` (``os.pathsep``-separated), else home."""
        home = Path.home().resolve()
        entries = (
            Path(entry.strip()).expanduser()
            for entry in os.environ.get(ALLOWED_ROOTS_ENV, "").split(os.pathsep)
            if entry.strip()
        )
        parents = tuple(entry.resolve() for entry in entries if entry.is_absolute())
        return cls(home=home, allowed_parents=parents or (home,))

    def refusal(self, root: PurePath) -> RootRefusal | None:
        """Why the resolved absolute *root* may not be registered, or None."""
        if root.parent == root:
            return RootRefusal.FILESYSTEM_ROOT
        if root == self.home:
            return RootRefusal.HOME_FOLDER
        if root in self.allowed_parents:
            return RootRefusal.ALLOWED_PARENT
        if not any(root.is_relative_to(parent) for parent in self.allowed_parents):
            return RootRefusal.OUTSIDE_ALLOWED_PARENTS
        return None

    def explain(self, root: PurePath, refusal: RootRefusal) -> str:
        parents = ", ".join(str(parent) for parent in self.allowed_parents)
        return (
            f"{root} {_REFUSAL_TEXT[refusal]}. A workspace root must be a folder "
            f"inside one of: {parents}. {ALLOWED_ROOTS_ENV} sets these folders."
        )


def _absolute_path(raw: str) -> Path:
    _reject_traversal(raw)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise WorkspacePathError(
            400, "PATH_NOT_ABSOLUTE", "Workspace paths must be absolute", raw
        )
    return path


def _resolve_root(path: Path) -> Path:
    # A share root is refused as it is; resolve() would look the server up on
    # the network first.
    return path if path.parent == path else path.resolve()


def absolute_path(raw: str) -> Path:
    """Resolve a path the caller names to inspect, without registering it."""
    return _absolute_path(raw).resolve()


def new_workspace_root(raw: str) -> Path:
    """Resolve a path the caller is about to register, refusing a disallowed root."""
    root = _resolve_root(_absolute_path(raw))
    policy = RootPolicy.from_env()
    refusal = policy.refusal(root)
    if refusal is not None:
        raise WorkspacePathError(
            403,
            "WORKSPACE_ROOT_NOT_ALLOWED",
            policy.explain(root, refusal),
            raw,
            {
                "reason": refusal,
                "allowed_parents": [str(parent) for parent in policy.allowed_parents],
            },
        )
    return root


class WorkspaceRootNotAllowed(BaseModel):
    """A registered workspace whose root is not inside an allowed parent folder."""

    workspace_id: str
    workspace_name: str
    root_path: str
    reason: RootRefusal
    message: str


def roots_not_allowed(engine) -> list[WorkspaceRootNotAllowed]:
    """Registered workspaces outside the allowed parents.

    They were registered before the limit or under another setting. They keep
    working, and bootstrap refuses to register them again.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, workspace_name, root_path FROM workspaces "
                "ORDER BY created_at"
            )
        ).fetchall()
    policy = RootPolicy.from_env()
    found: list[WorkspaceRootNotAllowed] = []
    for workspace_id, name, root_path in rows:
        if not root_path:
            continue
        root = _resolve_root(Path(str(root_path)).expanduser())
        refusal = policy.refusal(root)
        if refusal is None:
            continue
        found.append(
            WorkspaceRootNotAllowed(
                workspace_id=str(workspace_id),
                workspace_name=str(name),
                root_path=str(root),
                reason=refusal,
                message=(
                    f"Workspace '{name}': {policy.explain(root, refusal)} It was "
                    "registered before, so it keeps working, but bootstrap "
                    "refuses it. Move the folder inside an allowed parent and run "
                    "`molabel workspace bootstrap` there, or add its parent "
                    f"folder to {ALLOWED_ROOTS_ENV}."
                ),
            )
        )
    return found


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
