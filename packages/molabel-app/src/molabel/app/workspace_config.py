"""Config files in the workspace folder, and the manifest that lists them.

Task schemas, prompts and workflows are YAML files in the workspace folder,
listed in ``workbench.project.yaml``. Their database rows are an index of
those files. API creates and updates write the file, the manifest and the
row as one unit (see ``workspace_files``), and ``workspace bootstrap``
rewrites the rows from the files, so the file wins when the two disagree.
Datasets are listed in the manifest too; their imported records are review
state and live only in the database.
"""

from __future__ import annotations

import errno
import os
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from filelock import FileLock
from sqlalchemy import text

from molabel.app.workspace_paths import WorkspacePathError, resolve_in_workspace
from molabel.core.manifest import (
    DatasetManifestEntry,
    PromptManifestEntry,
    TaskSchemaManifestEntry,
    WorkflowManifestEntry,
    WorkspaceManifest,
    dump_manifest,
    load_manifest,
)

MANIFEST_FILENAME = "workbench.project.yaml"
_CORE_VERSION = "0.1.0"


@dataclass(frozen=True)
class ConfigKind:
    """Where one kind of config file lives and how the manifest lists it."""

    directory: str
    manifest_list: str
    id_field: str
    entry: Callable[[str, str], Any]


TASK_SCHEMA = ConfigKind(
    directory="workbench/config/task-schemas",
    manifest_list="task_schemas",
    id_field="task_schema_id",
    entry=lambda slug, path: TaskSchemaManifestEntry(
        task_schema_id=slug, definition_path=path
    ),
)
PROMPT = ConfigKind(
    directory="workbench/prompts",
    manifest_list="prompts",
    id_field="prompt_id",
    entry=lambda slug, path: PromptManifestEntry(prompt_id=slug, definition_path=path),
)
WORKFLOW = ConfigKind(
    directory="workbench/workflows",
    manifest_list="workflows",
    id_field="workflow_id",
    entry=lambda slug, path: WorkflowManifestEntry(
        workflow_id=slug, definition_path=path
    ),
)


@dataclass(frozen=True)
class WorkspaceFolder:
    workspace_id: str
    name: str
    path: Path


def workspace_folder(engine, workspace_id: str) -> WorkspaceFolder:
    """The folder of workspace *workspace_id*, which must exist on disk."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT workspace_name, root_path FROM workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    root = Path(str(row[1] or "")).expanduser().resolve()
    if not row[1] or not root.is_dir():
        raise WorkspacePathError(
            409,
            "WORKSPACE_FOLDER_MISSING",
            "The workspace folder does not exist; bootstrap it first",
            str(row[1] or ""),
        )
    return WorkspaceFolder(workspace_id, str(row[0]), root)


def _write_atomically(path: Path, content: str | bytes) -> None:
    """Replace *path* with *content*, refusing a file its owner made read-only."""
    if path.exists() and not path.stat().st_mode & stat.S_IWUSR:
        raise PermissionError(errno.EACCES, "The file is read-only", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        if isinstance(content, str):
            temp.write_text(content, encoding="utf-8")
        else:
            temp.write_bytes(content)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class WorkspaceFiles:
    """The config files and manifest that one request writes in a workspace."""

    def __init__(self, folder: WorkspaceFolder) -> None:
        self.folder = folder
        self._originals: dict[Path, bytes | None] = {}

    def write_config(
        self,
        kind: ConfigKind,
        *,
        slug: str,
        document: dict[str, Any],
        file_path: str | None,
        overwrite: bool,
    ) -> str:
        """Write *document* as the file for *slug* and list it in the manifest.

        With ``overwrite=False`` an existing file is left as it is: it is the
        source, and the caller is registering it. Returns the path relative
        to the workspace folder.
        """
        target = resolve_in_workspace(
            self.folder.path, file_path or f"{kind.directory}/{slug}.yaml"
        )
        if overwrite or not target.exists():
            self._write(
                target, yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
            )
        relative = target.relative_to(self.folder.path).as_posix()

        def list_file(manifest: WorkspaceManifest) -> None:
            entries = getattr(manifest, kind.manifest_list)
            kept = [e for e in entries if getattr(e, kind.id_field) != slug]
            setattr(manifest, kind.manifest_list, [*kept, kind.entry(slug, relative)])

        self._update_manifest(list_file)
        return relative

    def list_dataset(self, entry: DatasetManifestEntry) -> None:
        """Add or replace the manifest entry for a dataset."""

        def list_entry(manifest: WorkspaceManifest) -> None:
            kept = [d for d in manifest.datasets if d.dataset_id != entry.dataset_id]
            manifest.datasets = [*kept, entry]

        self._update_manifest(list_entry)

    def add_dataset_source(self, dataset_id: str, path: str) -> None:
        """Record that *path*, relative to the workspace, was imported."""

        def add_source(manifest: WorkspaceManifest) -> None:
            entry = next(
                (d for d in manifest.datasets if d.dataset_id == dataset_id), None
            )
            if entry is None:
                manifest.datasets.append(
                    DatasetManifestEntry(dataset_id=dataset_id, source_paths=[path])
                )
            elif path not in entry.source_paths:
                entry.source_paths.append(path)

        self._update_manifest(add_source)

    def _update_manifest(self, change: Callable[[WorkspaceManifest], None]) -> None:
        path = resolve_in_workspace(self.folder.path, MANIFEST_FILENAME)
        manifest = (
            load_manifest(path)
            if path.is_file()
            else WorkspaceManifest(
                workspace_id=self.folder.workspace_id,
                workspace_name=self.folder.name,
                core_version=_CORE_VERSION,
            )
        )
        change(manifest)
        self._write(path, dump_manifest(manifest))

    def _write(self, path: Path, content: str) -> None:
        original = path.read_bytes() if path.exists() else None
        try:
            _write_atomically(path, content)
        except OSError as exc:
            relative = path.relative_to(self.folder.path).as_posix()
            raise WorkspacePathError(
                409,
                "WORKSPACE_FILE_NOT_WRITABLE",
                f"Cannot write {relative}: {exc.strerror or exc}",
                relative,
            ) from exc
        self._originals.setdefault(path, original)

    def _restore(self) -> None:
        for path, original in reversed(self._originals.items()):
            if original is None:
                path.unlink(missing_ok=True)
            else:
                _write_atomically(path, original)


WORKSPACE_STATE_DIR = ".molabel"


def workspace_lock(root: Path) -> FileLock:
    """The OS-level lock every writer of files in the workspace at *root* holds.

    Take it before any database write, so writers wait for each other in one
    order and a rollback in ``workspace_files`` can only undo its own writes.
    The lock file lives in the workspace, so every writer shares it whatever
    its data directory, under ``.molabel/``, which ignores itself in git.
    """
    state_dir = resolve_in_workspace(root, WORKSPACE_STATE_DIR)
    (state_dir / "locks").mkdir(parents=True, exist_ok=True)
    ignore = resolve_in_workspace(root, f"{WORKSPACE_STATE_DIR}/.gitignore")
    if not ignore.exists():
        _write_atomically(ignore, "*\n")
    return FileLock(
        resolve_in_workspace(root, f"{WORKSPACE_STATE_DIR}/locks/workspace.lock")
    )


@contextmanager
def workspace_files(folder: WorkspaceFolder) -> Iterator[WorkspaceFiles]:
    """Write config files and commit their rows as one unit.

    Holds ``workspace_lock``, so other writers, in this server process or
    another, wait their turn. Commit the database inside the block, as its
    last step: if anything in the block raises, every file it wrote gets its
    old content back, or is removed if it is new.
    """
    with workspace_lock(folder.path):
        files = WorkspaceFiles(folder)
        try:
            yield files
        except BaseException:
            files._restore()
            raise


def read_config(folder: WorkspaceFolder, definition_path: str) -> dict[str, Any]:
    """Parse a listed config file into a mapping."""
    path = resolve_in_workspace(folder.path, definition_path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{definition_path} does not contain a mapping")
    return loaded
